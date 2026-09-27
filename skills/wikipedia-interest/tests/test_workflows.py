"""Offline end-to-end CLI scenarios with Wikimedia-shaped API fixtures."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import pypdfium2 as pdfium

from wikipedia_interest.cli import main
from wikipedia_interest.resolver import article_url


PROMPTS = {
    "fasting": "Порівняй інтерес до інтервального голодування в польській та чеській Wikipedia за 2023–2024 роки.",
    "astronomy": "Чи зростав інтерес до астрономії в україномовній Wikipedia за 2023–2024 роки?",
    "english": "Порівняй інтерес до вивчення англійської у pl, cs та uk і підготуй PDF.",
    "add_language": "Додай англійський розділ до аналізу астрономії.",
    "exclude_peak": "Виключи аномальний пік у грудні 2024 року і поясни, чи змінився висновок.",
}


def _page(language, title, links=None):
    return {"title": title, "url": article_url(language, title), "namespace": 0,
            "disambiguation": False, "redirected_from": None, "langlinks": links or {}}


PAGES = {
    ("en", "Intermittent fasting"): _page("en", "Intermittent fasting",
                                           {"pl": "Post przerywany", "cs": "Přerušovaný půst"}),
    ("pl", "Post przerywany"): _page("pl", "Post przerywany"),
    ("cs", "Přerušovaný půst"): _page("cs", "Přerušovaný půst"),
    ("uk", "Астрономія"): _page("uk", "Астрономія", {"en": "Astronomy"}),
    ("en", "Astronomy"): _page("en", "Astronomy", {"uk": "Астрономія"}),
    ("en", "English as a second language"): _page("en", "English as a second language",
        {"pl": "Angielski jako drugi język", "cs": "Angličtina jako druhý jazyk",
         "uk": "Англійська як друга мова"}),
    ("pl", "Angielski jako drugi język"): _page("pl", "Angielski jako drugi język"),
    ("cs", "Angličtina jako druhý jazyk"): _page("cs", "Angličtina jako druhý jazyk"),
    ("uk", "Англійська як друга мова"): _page("uk", "Англійська як друга мова"),
}


class FixtureWiki:
    def __init__(self, contact):
        self.contact = contact

    def page(self, language, title):
        return copy.deepcopy(PAGES.get((language, title)))

    def search(self, language, phrase):
        return []


class FixturePageviews:
    calls = []

    def __init__(self, contact):
        self.contact = contact

    def fetch(self, url):
        self.calls.append(url)
        parts = urllib.parse.urlparse(url).path.split("/")
        project, article, start, end = parts[-7], urllib.parse.unquote(parts[-4]).replace("_", " "), parts[-2], parts[-1]
        language = project.split(".")[0]
        items = []
        for year in range(int(start[:4]), int(end[:4]) + 1):
            for month in range(1, 13):
                stamp = f"{year:04d}{month:02d}01"
                if start <= stamp <= end:
                    index = (year - 2023) * 12 + month - 1
                    if language == "uk" and article == "Астрономія":
                        views = 1000 if index == 23 else 100
                    else:
                        base = {"pl": 130, "cs": 120, "en": 180, "uk": 110}[language]
                        views = base + index * 4
                    items.append({"project": project.removesuffix(".org"), "article": article,
                                  "access": "all-access", "agent": "user", "granularity": "monthly",
                                  "timestamp": stamp + "00", "views": views})
        return {"items": items}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.contact = "fixture@example.org"
        FixturePageviews.calls = []
        self.wiki_patch = patch("wikipedia_interest.cli.MediaWikiClient", FixtureWiki)
        self.views_patch = patch("wikipedia_interest.cli.PageviewsClient", FixturePageviews)
        self.run_wiki_patch = patch("wikipedia_interest.workflow.MediaWikiClient", FixtureWiki)
        self.run_views_patch = patch("wikipedia_interest.workflow.PageviewsClient", FixturePageviews)
        self.wiki_patch.start()
        self.views_patch.start()
        self.run_wiki_patch.start()
        self.run_views_patch.start()
        self.addCleanup(self.wiki_patch.stop)
        self.addCleanup(self.views_patch.stop)
        self.addCleanup(self.run_wiki_patch.stop)
        self.addCleanup(self.run_views_patch.stop)

    def command(self, command, *options):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([command, *map(str, options)]), 0)
        return json.loads(output.getvalue())

    def pipeline(self, name, *, topic, languages, overrides=(), exclusion=None):
        directory = self.root / name
        directory.mkdir()
        resolved_path, series_path = directory / "resolved.json", directory / "series.json"
        analysis_path = directory / "analysis.json"
        resolved = self.command("resolve", "--topic", topic, "--languages", *languages,
                                *[value for page in overrides for value in ("--page", page)],
                                "--contact", self.contact, "--output", resolved_path)
        self.assertEqual(resolved["status"], "resolved")
        fetched = self.command("fetch", "--resolved", resolved_path, "--start", "2023-01-01",
                               "--end", "2024-12-31", "--cache-dir", self.cache,
                               "--contact", self.contact, "--output", series_path)
        analyze_args = ["--series", series_path, "--output", analysis_path]
        if exclusion:
            analyze_args.extend(["--exclude-peak", exclusion])
        analyzed = self.command("analyze", *analyze_args)
        chart, pdf = directory / "chart.png", directory / "report.pdf"
        plotted = self.command("plot", "--analysis", analysis_path, "--output", chart)
        reported = self.command("report", "--analysis", analysis_path,
                                "--chart", chart, "--output", pdf)
        document = pdfium.PdfDocument(str(pdf))
        self.assertEqual(len(document), 1)
        pdf_text = document[0].get_textpage().get_text_range()
        document.close()
        self.assertEqual(reported["pages"], 1)
        self.assertEqual(plotted["status"], "ok")
        for metric in analyzed["metrics"]:
            self.assertIn(metric["title"], pdf_text)
            self.assertIn(f"{metric['metrics']['comparison']['percent_change']:+.1f}%", pdf_text)
        return resolved, fetched, analyzed, pdf_text

    def test_three_initial_prompts_finish_with_pdf_from_api_fixtures(self):
        self.assertIn("польській", PROMPTS["fasting"])
        fasting = self.pipeline("fasting", topic="Intermittent fasting", languages=("pl", "cs"))
        self.assertEqual([row["match_method"] for row in fasting[0]["resolved_pages"]],
                         ["interlanguage_link", "interlanguage_link"])
        self.assertEqual(len(fasting[2]["metrics"]), 2)
        self.assertIn("астрономії", PROMPTS["astronomy"])
        astronomy = self.pipeline("astronomy", topic="Астрономія", languages=("uk",))
        self.assertEqual(astronomy[2]["metrics"][0]["metrics"]["agreement"], "uncertain")
        self.assertIn("вивчення англійської", PROMPTS["english"])
        english = self.pipeline("english", topic="English as a second language",
                                languages=("pl", "cs", "uk"))
        self.assertEqual(len(english[2]["metrics"]), 3)

    def test_add_language_reuses_old_chunks_and_exclusion_changes_conclusion(self):
        self.assertIn("Додай", PROMPTS["add_language"])
        first = self.pipeline("first", topic="Астрономія", languages=("uk",))
        self.assertEqual(first[1]["cache"], {"hits": 0, "misses": 2,
                                              "directory": str(self.cache.resolve())})
        second = self.pipeline("second", topic="Астрономія", languages=("uk", "en"))
        self.assertEqual(second[1]["cache"]["hits"], 2)
        self.assertEqual(second[1]["cache"]["misses"], 2)
        self.assertEqual(len(FixturePageviews.calls), 4)
        self.assertIn("Виключи", PROMPTS["exclude_peak"])
        # Reuse the saved series: only analysis, chart and report change.
        analysis_path = self.root / "first" / "analysis.json"
        series_path = self.root / "first" / "series.json"
        alternative = self.command("analyze", "--series", series_path,
            "--exclude-peak", "uk=2024-12-01:разовий пік", "--output", analysis_path)
        self.assertTrue(alternative["alternatives"][0]["conclusion_changed"])
        self.assertEqual(alternative["alternatives"][0]["alternative_agreement"],
                         "no_convincing_change")
        self.assertEqual(len(FixturePageviews.calls), 4)
        chart, pdf = self.root / "first" / "chart.png", self.root / "first" / "report.pdf"
        self.command("report", "--analysis", analysis_path, "--chart", chart, "--output", pdf)
        document = pdfium.PdfDocument(str(pdf))
        text = document[0].get_textpage().get_text_range()
        document.close()
        self.assertIn("разовий пік", text)
        self.assertIn("Невизначено → Без зміни", text)

    def test_one_command_run_and_safe_unresolved_stop(self):
        directory = self.root / "one-command"
        result = self.command("run", "--topic", "Астрономія", "--languages", "uk",
                              "--start", "2023-01-01", "--end", "2024-12-31",
                              "--contact", self.contact, "--cache-dir", self.cache,
                              "--artifact-dir", directory)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["pdf_pages"], 1)
        self.assertEqual(result["cache"]["misses"], 2)
        self.assertEqual(result["metrics"][0]["agreement"], "uncertain")
        self.assertTrue(Path(result["artifacts"]["pdf"]).is_file())
        self.assertEqual(len(FixturePageviews.calls), 2)

        reused = self.command("run", "--resolved", result["artifacts"]["resolved"],
                              "--start", "2023-01-01", "--end", "2024-12-31",
                              "--contact", self.contact, "--cache-dir", self.cache,
                              "--artifact-dir", self.root / "reused")
        self.assertEqual(reused["cache"]["hits"], 2)
        self.assertEqual(reused["cache"]["misses"], 0)
        self.assertEqual(len(FixturePageviews.calls), 2)

        unresolved_dir = self.root / "unresolved"
        unresolved = self.command("run", "--topic", "Unknown concept",
                                  "--languages", "pl", "cs", "--start", "2023-01-01",
                                  "--end", "2024-12-31", "--contact", self.contact,
                                  "--cache-dir", self.cache, "--artifact-dir", unresolved_dir)
        self.assertEqual(unresolved["status"], "needs_confirmation")
        self.assertTrue((unresolved_dir / "resolved_pages.json").is_file())
        self.assertFalse((unresolved_dir / "report.pdf").exists())

    def test_rerun_rejects_existing_artifacts_before_resolving(self):
        directory = self.root / "existing"
        directory.mkdir()
        for name in ("resolved_pages.json", "series.json", "analysis.json", "chart.png", "report.pdf"):
            with self.subTest(name=name):
                existing = directory / name
                existing.write_bytes(b"previous run")
                error = io.StringIO()
                with contextlib.redirect_stderr(error), patch(
                        "wikipedia_interest.workflow.resolve_topic") as resolve:
                    status = main(["run", "--topic", "Unknown concept", "--languages", "uk",
                                   "--start", "2023-01-01", "--end", "2024-12-31",
                                   "--contact", self.contact, "--cache-dir", str(self.cache),
                                   "--artifact-dir", str(directory)])
                self.assertEqual(status, 1)
                self.assertIn("Choose a new --artifact-dir", json.loads(error.getvalue())["message"])
                resolve.assert_not_called()
                self.assertEqual(existing.read_bytes(), b"previous run")
                self.assertEqual(list(directory.iterdir()), [existing])
                existing.unlink()


if __name__ == "__main__":
    unittest.main()
