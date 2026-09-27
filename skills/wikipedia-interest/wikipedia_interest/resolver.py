"""Resolve Wikipedia articles without guessing cross-language equivalence."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]+)*$")


class ResolutionError(Exception):
    """A remote response or input prevents reliable resolution."""


def validate_language(language: str) -> str:
    language = language.lower().strip()
    if not LANGUAGE.fullmatch(language):
        raise ValueError(f"Invalid Wikipedia language code: {language!r}")
    return language


def article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'), safe='')}"


def parse_page_input(language: str, value: str) -> str:
    """Accept a title or a matching language-edition /wiki/ URL."""
    value = value.strip()
    if not value:
        raise ValueError(f"Empty page for {language}")
    if "://" not in value:
        return value.replace("_", " ")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != f"{language}.wikipedia.org":
        raise ValueError(f"Page URL must use https://{language}.wikipedia.org/wiki/")
    if not parsed.path.startswith("/wiki/") or len(parsed.path) <= len("/wiki/"):
        raise ValueError(f"Invalid Wikipedia article URL: {value}")
    return urllib.parse.unquote(parsed.path[len("/wiki/"):]).replace("_", " ")


@dataclass
class MediaWikiClient:
    contact: str
    timeout: float = 10.0

    def __post_init__(self):
        if not self.contact.strip() or not ("@" in self.contact or self.contact.startswith("https://")):
            raise ValueError("--contact must be an email address or HTTPS contact URL")

    def query(self, language: str, **params) -> dict:
        params = {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5", **params}
        url = f"https://{language}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": f"WikipediaInterest/0.2 ({self.contact}) Python-urllib"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ResolutionError(f"Wikipedia API request failed for {language}: {exc}") from exc
        if "error" in payload:
            raise ResolutionError(f"Wikipedia API error for {language}: {payload['error']}")
        return payload

    def page(self, language: str, title: str) -> dict | None:
        params = {
            "titles": title,
            "redirects": "1",
            "prop": "info|pageprops|langlinks",
            "inprop": "url",
            "lllimit": "max",
        }
        langlinks = {}
        page = None
        redirected_from = None
        while True:
            payload = self.query(language, **params)
            query = payload.get("query", {})
            pages = query.get("pages", [])
            if len(pages) != 1:
                raise ResolutionError(f"Unexpected page response for {language}:{title}")
            page = pages[0]
            if page.get("missing") or page.get("invalid"):
                return None
            redirects = query.get("redirects", [])
            if redirects:
                redirected_from = redirects[0].get("from")
            for link in page.get("langlinks", []):
                langlinks[link["lang"]] = link["title"]
            if "continue" not in payload:
                break
            params.update(payload["continue"])
        return {
            "title": page["title"],
            "url": page.get("fullurl") or article_url(language, page["title"]),
            "namespace": page.get("ns"),
            "disambiguation": "disambiguation" in page.get("pageprops", {}),
            "redirected_from": redirected_from,
            "langlinks": langlinks,
        }

    def search(self, language: str, phrase: str) -> list[str]:
        payload = self.query(language, list="search", srsearch=phrase, srnamespace="0", srlimit="5")
        return [item["title"] for item in payload.get("query", {}).get("search", [])]


def _candidate_list(client, language: str, phrase: str) -> list[dict]:
    return [{"title": title, "url": article_url(language, title)} for title in client.search(language, phrase)[:5]]


def _record(language: str, page: dict | None, method: str, status: str,
            warnings: list[str] | None = None, candidates: list[dict] | None = None) -> dict:
    return {
        "language": language,
        "project": f"{language}.wikipedia.org",
        "status": status,
        "title": page["title"] if page else None,
        "url": page["url"] if page else None,
        "match_method": method,
        "warnings": warnings or [],
        "candidates": candidates or [],
    }


def resolve_topic(client, topic: str | None, languages: list[str],
                  overrides: dict[str, str] | None = None) -> dict:
    """Return verified pages and explicit uncertainty for unresolved matches."""
    languages = [validate_language(lang) for lang in languages]
    if not languages or len(languages) != len(set(languages)):
        raise ValueError("Provide one or more distinct languages")
    overrides = {validate_language(lang): value for lang, value in (overrides or {}).items()}
    if set(overrides) - set(languages):
        raise ValueError("Every --page language must appear in --languages")
    topic = (topic or "").strip()
    if not topic and not overrides:
        raise ValueError("Provide --topic or at least one --page")

    queried_languages = set()
    verified = {}
    for lang, value in overrides.items():
        title = parse_page_input(lang, value)
        queried_languages.add(lang)
        verified[lang] = client.page(lang, title)

    seed_lang = next((lang for lang in languages if verified.get(lang)), None)
    seed = verified.get(seed_lang) if seed_lang else None
    seed_confirmed = bool(seed)
    search_candidates = {}

    if not seed and topic:
        # An exact, existing article is a stronger seed than a search result.
        seed_order = ["en", *languages] if topic.isascii() else [*languages, "en"]
        for lang in dict.fromkeys(seed_order):
            queried_languages.add(lang)
            exact = client.page(lang, topic)
            if exact and exact["namespace"] == 0:
                seed_lang, seed, seed_confirmed = lang, exact, True
                break
        if not seed:
            for lang in dict.fromkeys(seed_order):
                queried_languages.add(lang)
                candidates = _candidate_list(client, lang, topic)
                search_candidates[lang] = candidates
                if candidates:
                    seed_lang = lang
                    seed = client.page(lang, candidates[0]["title"])
                    seed_confirmed = False
                    break

    records = []
    for lang in languages:
        if lang in overrides:
            page = verified[lang]
            if not page or page["namespace"] != 0:
                records.append(_record(lang, None, "user_page", "missing", ["page_missing_or_not_article"]))
                continue
            warnings = []
            if page["disambiguation"]:
                warnings.append("disambiguation_page")
            if page["redirected_from"]:
                warnings.append("redirected_from:" + page["redirected_from"])
            if seed and lang != seed_lang:
                if lang not in seed["langlinks"]:
                    warnings.append("semantic_equivalence_unverified")
                elif page["title"] != seed["langlinks"][lang]:
                    warnings.append("semantic_mismatch_with_seed_langlink")
            status = "needs_confirmation" if page["disambiguation"] else "selected"
            records.append(_record(lang, page, "user_page", status, warnings))
            continue

        if seed and lang == seed_lang:
            warnings = ["disambiguation_page"] if seed["disambiguation"] else []
            if not seed_confirmed:
                warnings.append("unconfirmed_search_seed")
            status = "selected" if seed_confirmed and not warnings else "needs_confirmation"
            method = "exact_title" if seed_confirmed else "search_candidate"
            records.append(_record(lang, seed, method, status, warnings,
                                   search_candidates.get(lang) if not seed_confirmed else None))
            continue

        linked_title = seed["langlinks"].get(lang) if seed else None
        if linked_title:
            queried_languages.add(lang)
            page = client.page(lang, linked_title)
            if page and page["namespace"] == 0:
                warnings = ["disambiguation_page"] if page["disambiguation"] else []
                if not seed_confirmed:
                    warnings.append("unconfirmed_search_seed")
                if page["title"] != linked_title:
                    warnings.append("linked_title_redirected")
                status = "selected" if seed_confirmed and not warnings and not seed["disambiguation"] else "needs_confirmation"
                records.append(_record(lang, page, "interlanguage_link", status, warnings))
                continue

        # Searching an English phrase on another-language wiki commonly returns
        # unrelated text matches. A missing langlink needs a human supplied page.
        candidates = search_candidates.get(lang) if not seed else None
        warnings = ["no_verified_interlanguage_match"] if seed else ["no_seed_article"]
        records.append(_record(lang, None, "search_candidate" if candidates else "none",
                               "needs_confirmation" if candidates else "missing",
                               warnings, candidates))

    status = "resolved" if all(record["status"] == "selected" for record in records) else "needs_confirmation"
    return {
        "status": status,
        "request": {"topic": topic or None, "languages": languages, "page_overrides": overrides},
        "seed": {"language": seed_lang, "title": seed["title"], "url": seed["url"],
                 "confirmed": seed_confirmed} if seed else None,
        "resolved_pages": records,
        "next_action": "Review titles and URLs; rerun with --page LANGUAGE=TITLE_OR_URL for uncertain matches."
                       if status != "resolved" else "Review selected titles and URLs before fetching pageviews.",
        "sources": [f"https://{lang}.wikipedia.org/w/api.php"
                    for lang in sorted(queried_languages)],
    }
