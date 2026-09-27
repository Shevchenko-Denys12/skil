"""Command-line interface; behavior lives in the skill modules."""

import argparse
import json
import sys
from pathlib import Path

from .environment import SKILL_ROOT, check_environment
from .analysis import analyze_trend
from .pageviews import PageviewsClient, PageviewsError, fetch_pageviews
from .plot import plot_chart
from .report import report_pdf
from .resolver import MediaWikiClient, ResolutionError, resolve_topic
from .workflow import run_workflow


def _page_overrides(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--page must be LANGUAGE=TITLE_OR_URL")
        language, page = value.split("=", 1)
        if language in result:
            raise ValueError(f"Duplicate --page for {language}")
        result[language] = page
    return result


def _peak_exclusions(values: list[str]) -> dict[str, dict]:
    result = {}
    for value in values:
        if "=" not in value or ":" not in value.split("=", 1)[1]:
            raise ValueError("--exclude-peak must be LANGUAGE=YYYY-MM-DD:REASON")
        language, rest = value.split("=", 1)
        peak_date, reason = rest.split(":", 1)
        if language in result:
            raise ValueError(f"Duplicate --exclude-peak for {language}")
        result[language] = {"date": peak_date, "reason": reason}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wikipedia interest skill tools")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check work directories and available capabilities")
    doctor.add_argument("--cache-dir", type=Path, required=True)
    doctor.add_argument("--artifact-dir", type=Path, required=True)
    resolver = commands.add_parser("resolve", help="resolve and verify Wikipedia articles")
    resolver.add_argument("--topic", help="topic text or exact Wikipedia title")
    resolver.add_argument("--languages", nargs="+", required=True, metavar="LANG")
    resolver.add_argument("--page", action="append", default=[], metavar="LANG=TITLE_OR_URL",
                          help="explicit article; repeat for multiple languages")
    resolver.add_argument("--contact", required=True, help="email or HTTPS contact URL for User-Agent")
    resolver.add_argument("--output", type=Path, help="save identical JSON to this file")
    fetcher = commands.add_parser("fetch", help="fetch and cache per-article Pageviews")
    fetcher.add_argument("--resolved", type=Path, required=True, help="JSON from resolve_topic.py")
    fetcher.add_argument("--start", required=True, help="inclusive YYYY-MM-DD")
    fetcher.add_argument("--end", required=True, help="inclusive YYYY-MM-DD")
    fetcher.add_argument("--granularity", choices=["monthly", "daily"], default="monthly")
    fetcher.add_argument("--access", choices=["all-access", "desktop", "mobile-web", "mobile-app"], default="all-access")
    fetcher.add_argument("--agent", choices=["user", "all-agents", "spider"], default="user")
    fetcher.add_argument("--cache-dir", type=Path, required=True)
    fetcher.add_argument("--contact", required=True, help="email or HTTPS contact URL for User-Agent")
    fetcher.add_argument("--output", type=Path, help="save identical JSON outside skill directory")
    analyzer = commands.add_parser("analyze", help="calculate trend signals from monthly series")
    analyzer.add_argument("--series", type=Path, required=True, help="JSON from fetch_pageviews.py")
    analyzer.add_argument("--criterion-json", type=Path, help="optional JSON file with threshold criteria")
    analyzer.add_argument("--exclude-peak", action="append", default=[], metavar="LANG=YYYY-MM-DD:REASON")
    analyzer.add_argument("--output", type=Path, help="save identical JSON outside skill directory")
    plotter = commands.add_parser("plot", help="draw a PNG from analyzed JSON")
    plotter.add_argument("--analysis", type=Path, required=True)
    plotter.add_argument("--output", type=Path, required=True)
    plotter.add_argument("--language", choices=["uk", "en"], default="uk")
    reporter = commands.add_parser("report", help="create a one-page PDF and matching PNG")
    reporter.add_argument("--analysis", type=Path, required=True)
    reporter.add_argument("--chart", type=Path, required=True)
    reporter.add_argument("--output", type=Path, required=True)
    reporter.add_argument("--language", choices=["uk", "en"], default="uk")
    runner = commands.add_parser("run", help="resolve, fetch, analyze and write the one-page report")
    runner.add_argument("--topic", help="topic text or exact Wikipedia title")
    runner.add_argument("--languages", nargs="+", metavar="LANG")
    runner.add_argument("--page", action="append", default=[], metavar="LANG=TITLE_OR_URL")
    runner.add_argument("--resolved", type=Path, help="reuse a verified resolver JSON")
    runner.add_argument("--start", required=True, help="inclusive YYYY-MM-DD")
    runner.add_argument("--end", required=True, help="inclusive YYYY-MM-DD")
    runner.add_argument("--contact", required=True, help="email or HTTPS contact URL for User-Agent")
    runner.add_argument("--cache-dir", type=Path, required=True)
    runner.add_argument("--artifact-dir", type=Path, required=True)
    runner.add_argument("--criterion-json", type=Path)
    runner.add_argument("--exclude-peak", action="append", default=[], metavar="LANG=YYYY-MM-DD:REASON")
    runner.add_argument("--language", choices=["uk", "en"], default="uk")
    args = parser.parse_args(argv)

    try:
        if args.command == "doctor":
            result = check_environment(args.cache_dir, args.artifact_dir)
        elif args.command == "resolve":
            client = MediaWikiClient(args.contact)
            result = resolve_topic(client, args.topic, args.languages, _page_overrides(args.page))
            if args.output:
                if args.output.resolve().is_relative_to(SKILL_ROOT):
                    raise ValueError("--output must be outside the skill directory")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.command == "fetch":
            if args.output and args.output.resolve().is_relative_to(SKILL_ROOT):
                raise ValueError("--output must be outside the skill directory")
            resolved = json.loads(args.resolved.read_text(encoding="utf-8"))
            result = fetch_pageviews(resolved, start=args.start, end=args.end,
                                     cache_dir=args.cache_dir, client=PageviewsClient(args.contact),
                                     access=args.access, agent=args.agent,
                                     granularity=args.granularity)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.command == "analyze":
            if args.output and args.output.resolve().is_relative_to(SKILL_ROOT):
                raise ValueError("--output must be outside the skill directory")
            fetched = json.loads(args.series.read_text(encoding="utf-8"))
            criterion = (json.loads(args.criterion_json.read_text(encoding="utf-8"))
                         if args.criterion_json else None)
            result = analyze_trend(fetched, criterion=criterion,
                                   exclusions=_peak_exclusions(args.exclude_peak))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.command == "plot":
            analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
            result = plot_chart(analysis, args.output, args.language)
        elif args.command == "report":
            analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
            result = report_pdf(analysis, args.chart, args.output, args.language)
        else:
            criterion = (json.loads(args.criterion_json.read_text(encoding="utf-8"))
                         if args.criterion_json else None)
            result = run_workflow(topic=args.topic, languages=args.languages,
                                  pages=_page_overrides(args.page), resolved_path=args.resolved,
                                  start=args.start, end=args.end, contact=args.contact,
                                  cache_dir=args.cache_dir, artifact_dir=args.artifact_dir,
                                  criterion=criterion, exclusions=_peak_exclusions(args.exclude_peak),
                                  language=args.language)
    except (OSError, ValueError, KeyError, TypeError, ResolutionError, PageviewsError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
