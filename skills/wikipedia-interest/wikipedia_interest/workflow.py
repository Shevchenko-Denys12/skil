"""Thin orchestration of the independently testable skill stages."""

import json
from pathlib import Path

from .analysis import analyze_trend
from .environment import check_environment
from .pageviews import PageviewsClient, fetch_pageviews
from .report import report_pdf
from .resolver import MediaWikiClient, resolve_topic


def _save(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path.resolve())


def _summary(analysis: dict) -> list[dict]:
    result = []
    for item in analysis["metrics"]:
        signals = item["metrics"]
        result.append({
            "language": item["language"], "title": item["title"], "url": item["url"],
            "match_method": next(page.get("match_method") for page in analysis["resolved_pages"]
                                 if page["language"] == item["language"]),
            "comparison": signals["comparison"],
            "robust_trend": signals["robust_trend"],
            "agreement": signals["agreement"],
            "reliability": item["reliability"],
            "quality_flags": item["quality_flags"],
            "criterion_evaluation": item["criterion_evaluation"],
            "sources": item["sources"],
        })
    return result


def run_workflow(*, topic: str | None, languages: list[str] | None, pages: dict[str, str],
                 resolved_path: Path | None, start: str, end: str, contact: str,
                 cache_dir: Path, artifact_dir: Path, criterion: dict | None = None,
                 exclusions: dict[str, dict] | None = None, language: str = "uk") -> dict:
    """Produce a report, or stop with the resolver's explicit confirmation request."""
    check_environment(cache_dir, artifact_dir)
    outputs = ("resolved_pages.json", "series.json", "analysis.json", "chart.png", "report.pdf")
    occupied = [name for name in outputs if (artifact_dir / name).exists()
                or (artifact_dir / name).is_symlink()]
    if occupied:
        raise ValueError("Artifact directory already contains workflow outputs: "
                         + ", ".join(occupied) + ". Choose a new --artifact-dir; "
                         "reuse --cache-dir or --resolved to avoid repeating completed work.")
    if resolved_path is not None:
        if topic or pages:
            raise ValueError("--resolved cannot be combined with --topic or --page")
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
        if languages and [page["language"] for page in resolved.get("resolved_pages", [])] != languages:
            raise ValueError("--languages must match the saved resolved JSON")
    else:
        if not languages:
            raise ValueError("Provide --languages when resolving a topic")
        resolved = resolve_topic(MediaWikiClient(contact), topic, languages, pages)

    resolved_file = _save(artifact_dir / "resolved_pages.json", resolved)
    if resolved.get("status") != "resolved":
        return {"status": "needs_confirmation", "resolved_pages": resolved.get("resolved_pages", []),
                "next_action": resolved.get("next_action"), "artifacts": {"resolved": resolved_file}}

    fetched = fetch_pageviews(resolved, start=start, end=end, cache_dir=cache_dir,
                              client=PageviewsClient(contact))
    series_file = _save(artifact_dir / "series.json", fetched)
    analyzed = analyze_trend(fetched, criterion=criterion, exclusions=exclusions)
    analysis_file = _save(artifact_dir / "analysis.json", analyzed)
    chart_file, pdf_file = artifact_dir / "chart.png", artifact_dir / "report.pdf"
    report = report_pdf(analyzed, chart_file, pdf_file, language)
    return {
        "status": "complete", "request": analyzed["request"],
        "metrics": _summary(analyzed),
        "alternatives": analyzed["alternatives"],
        "assumptions": analyzed["assumptions"],
        "quality_flags": analyzed["quality_flags"],
        "cache": fetched["cache"],
        "artifacts": {"resolved": resolved_file, "series": series_file,
                      "analysis": analysis_file, "chart": report["chart"], "pdf": report["pdf"]},
        "pdf_pages": report["pages"],
    }
