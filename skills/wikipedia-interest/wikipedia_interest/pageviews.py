"""Fetch and cache Wikimedia per-article Pageviews without filling missing data."""

import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .environment import SKILL_ROOT


API_ROOT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
FIRST_DAY = date(2015, 7, 1)
ACCESS = {"all-access", "desktop", "mobile-web", "mobile-app"}
AGENTS = {"all-agents", "user", "spider"}
GRANULARITIES = {"monthly", "daily"}
FRESH_SECONDS = 3600
CACHE_SCHEMA_VERSION = 2
PROJECT = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]+)*\.wikipedia\.org$")


class PageviewsError(Exception):
    """The request, API response, or cache cannot yield a reliable series."""


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _month_end(day: date) -> date:
    return _next_month(day) - timedelta(days=1)


def _months(start: date, end: date):
    current = start.replace(day=1)
    while current <= end:
        yield current
        current = _next_month(current)


def _days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; use YYYY-MM-DD") from exc


def _validated_dates(start: str, end: str, today: date) -> tuple[date, date]:
    start_day, end_day = _parse_date(start), _parse_date(end)
    if start_day < FIRST_DAY:
        raise ValueError("Pageviews start on 2015-07-01")
    if start_day > end_day:
        raise ValueError("--start must be on or before --end")
    if end_day > today:
        raise ValueError("--end cannot be in the future")
    return start_day, end_day


def _chunks(start: date, end: date, granularity: str, today: date):
    """Reusable calendar chunks; current incomplete buckets have short TTL."""
    if granularity == "monthly":
        requested_months = list(_months(start, end))
        years = sorted({day.year for day in requested_months})
        current_month = today.replace(day=1)
        for year in years:
            year_start = max(date(year, 1, 1), FIRST_DAY)
            year_end = date(year, 12, 31)
            if year < today.year:
                yield year_start, year_end, False
            else:
                previous_month_end = current_month - timedelta(days=1)
                if year_start <= previous_month_end and any(day < current_month for day in requested_months):
                    yield year_start, previous_month_end, False
                if any(day == current_month for day in requested_months):
                    yield current_month, today, True
    else:
        current_month = today.replace(day=1)
        for month in _months(start, end):
            chunk_start = max(month, FIRST_DAY)
            if month < current_month:
                yield chunk_start, _month_end(month), False
            elif month == current_month:
                yesterday = today - timedelta(days=1)
                if chunk_start <= yesterday and start <= yesterday:
                    yield chunk_start, yesterday, False
                if end >= today:
                    yield today, today, True


def _api_url(project: str, title: str, access: str, agent: str,
             granularity: str, start: date, end: date) -> str:
    encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return (f"{API_ROOT}/{project}/{access}/{agent}/{encoded_title}/{granularity}/"
            f"{start:%Y%m%d}/{end:%Y%m%d}")


def _cache_key(project: str, title: str, access: str, agent: str,
               granularity: str, start: date, end: date) -> str:
    value = [project, title, access, agent, granularity, start.isoformat(), end.isoformat()]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass
class PageviewsClient:
    contact: str
    timeout: float = 15.0
    attempts: int = 3

    def __post_init__(self):
        if not self.contact.strip() or not ("@" in self.contact or self.contact.startswith("https://")):
            raise ValueError("--contact must be an email address or HTTPS contact URL")

    def fetch(self, url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": f"WikipediaInterest/0.3 ({self.contact}) Python-urllib",
                     "Accept": "application/json"},
        )
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise PageviewsError("Unexpected non-object API response")
                return payload
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {429, 500, 502, 503, 504}
                if retryable and attempt + 1 < self.attempts:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise PageviewsError(f"Pageviews API HTTP {exc.code} for {url}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt + 1 < self.attempts:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise PageviewsError(f"Pageviews API unavailable for {url}: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise PageviewsError(f"Invalid Pageviews API JSON for {url}") from exc
        raise PageviewsError("Pageviews API attempts exhausted")


def _normalize(payload: dict, *, project: str, title: str, access: str,
               agent: str, granularity: str, start: date, end: date,
               today: date) -> list[dict]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise PageviewsError("Pageviews API response has no items list")
    found = {}
    for item in items:
        if (item.get("project") not in {project, project.removesuffix(".org")}
                or item.get("access") != access
                or item.get("agent") != agent or item.get("granularity") != granularity):
            got = {field: item.get(field) for field in ("project", "access", "agent", "granularity")}
            expected = {"project": project, "access": access, "agent": agent,
                        "granularity": granularity}
            raise PageviewsError(f"Pageviews API metric definition differs from request: {got} != {expected}")
        timestamp = item.get("timestamp", "")
        try:
            bucket = datetime.strptime(timestamp[:8], "%Y%m%d").date()
        except (ValueError, TypeError) as exc:
            raise PageviewsError("Invalid Pageviews API timestamp") from exc
        if granularity == "monthly":
            bucket = bucket.replace(day=1)
        views = item.get("views")
        if not isinstance(views, int) or isinstance(views, bool) or views < 0:
            raise PageviewsError("Invalid Pageviews API views count")
        if bucket in found:
            raise PageviewsError("Duplicate Pageviews API timestamp")
        found[bucket] = views
    buckets = _months(start, end) if granularity == "monthly" else _days(start, end)
    current_month = today.replace(day=1)
    return [{"date": bucket.isoformat(), "views": found.get(bucket),
             "complete": bucket < (current_month if granularity == "monthly" else today),
             "missing": bucket not in found}
            for bucket in buckets]


def _same_title(left: str, right: str) -> bool:
    return unicodedata.normalize("NFC", left.replace("_", " ")) == unicodedata.normalize("NFC", right.replace("_", " "))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_chunk(cache_dir: Path, key: str, volatile: bool, now: datetime) -> dict | None:
    raw_path = cache_dir / "raw" / f"{key}.json"
    normalized_path = cache_dir / "normalized" / f"{key}.json"
    if not raw_path.is_file() or not normalized_path.is_file():
        return None
    try:
        saved = json.loads(normalized_path.read_text(encoding="utf-8"))
        if saved.get("schema_version") != CACHE_SCHEMA_VERSION or saved.get("cache_key") != key:
            return None
        if volatile and (now - datetime.fromisoformat(saved["fetched_at"])).total_seconds() >= FRESH_SECONDS:
            return None
        return saved
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fetch_pageviews(resolved: dict, *, start: str, end: str,
                    cache_dir: Path, client: PageviewsClient,
                    access: str = "all-access", agent: str = "user",
                    granularity: str = "monthly", today: date | None = None,
                    now: datetime | None = None) -> dict:
    """Fetch selected articles, reusing complete raw and normalized chunks."""
    today = today or datetime.now(timezone.utc).date()
    now = now or datetime.now(timezone.utc)
    start_day, end_day = _validated_dates(start, end, today)
    if access not in ACCESS or agent not in AGENTS or granularity not in GRANULARITIES:
        raise ValueError("Invalid access, agent, or granularity")
    if resolved.get("status") != "resolved" or not resolved.get("resolved_pages"):
        raise ValueError("Resolved input must have status 'resolved' and selected pages")
    if cache_dir.resolve().is_relative_to(SKILL_ROOT):
        raise ValueError("--cache-dir must be outside the skill directory")

    series = []
    sources = []
    hits = misses = 0
    for page in resolved["resolved_pages"]:
        if page.get("status") != "selected" or not page.get("title"):
            raise ValueError("Every resolved page must be selected and have a canonical title")
        project, title = page["project"], page["title"]
        if not PROJECT.fullmatch(project) or project != f"{page['language']}.wikipedia.org":
            raise ValueError("Resolved page has an invalid project")
        points = []
        page_sources = []
        chunk_details = []
        for chunk_start, chunk_end, volatile in _chunks(start_day, end_day, granularity, today):
            url = _api_url(project, title, access, agent, granularity, chunk_start, chunk_end)
            key = _cache_key(project, title, access, agent, granularity, chunk_start, chunk_end)
            saved = _load_chunk(cache_dir, key, volatile, now)
            cache_hit = saved is not None
            if saved is None:
                payload = client.fetch(url)
                normalized = _normalize(payload, project=project, title=title, access=access,
                                        agent=agent, granularity=granularity,
                                        start=chunk_start, end=chunk_end, today=today)
                api_articles = sorted({item["article"] for item in payload["items"]
                                       if isinstance(item.get("article"), str)})
                _write_json(cache_dir / "raw" / f"{key}.json", payload)
                saved = {"schema_version": CACHE_SCHEMA_VERSION, "cache_key": key,
                         "fetched_at": now.isoformat(), "url": url, "points": normalized,
                         "volatile": volatile, "api_articles": api_articles}
                _write_json(cache_dir / "normalized" / f"{key}.json", saved)
                misses += 1
            else:
                hits += 1
            points.extend(saved["points"])
            page_sources.append(url)
            sources.append(url)
            chunk_details.append({"url": url, "fetched_at": saved["fetched_at"],
                                  "cache_hit": cache_hit,
                                  "api_articles": saved.get("api_articles", [])})
        filter_start = start_day.replace(day=1) if granularity == "monthly" else start_day
        filter_end = end_day.replace(day=1) if granularity == "monthly" else end_day
        points = [point for point in points if filter_start <= date.fromisoformat(point["date"]) <= filter_end]
        flags = []
        if any(point["missing"] for point in points):
            flags.append("missing_points")
        if any(not point["complete"] for point in points):
            flags.append("incomplete_period")
        if any("redirect" in warning for warning in page.get("warnings", [])):
            flags.append("page_redirect_or_title_change_possible")
        if any(not _same_title(title, article)
               for detail in chunk_details for article in detail.get("api_articles", [])):
            flags.append("api_article_title_differs")
        if any("semantic" in warning for warning in page.get("warnings", [])):
            flags.append("semantic_equivalence_warning")
        series.append({"language": page["language"], "project": project,
                       "title": title, "url": page["url"], "access": access,
                       "agent": agent, "granularity": granularity,
                       "requested_start": start, "requested_end": end,
                       "points": points, "quality_flags": flags, "sources": page_sources,
                       "chunks": chunk_details})

    return {"status": "partial" if any(flag in {"missing_points", "incomplete_period"}
                                        for row in series for flag in row["quality_flags"]) else "ok",
            "request": {"topic": resolved.get("request", {}).get("topic"),
                        "languages": [row["language"] for row in series],
                        "start": start, "end": end, "access": access,
                        "agent": agent, "granularity": granularity},
            "resolved_pages": resolved["resolved_pages"],
            "series": series, "quality_flags": sorted({flag for row in series for flag in row["quality_flags"]}),
            "sources": list(dict.fromkeys(sources)),
            "cache": {"hits": hits, "misses": misses, "directory": str(cache_dir.resolve())}}
