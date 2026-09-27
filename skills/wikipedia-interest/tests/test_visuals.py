import tempfile
import unittest
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from wikipedia_interest.analysis import analyze_trend
from wikipedia_interest.plot import plot_chart
from wikipedia_interest.report import LABELS, _recommendation, report_pdf
from test_analysis import fetched


class VisualTests(unittest.TestCase):
    def test_growth_failing_business_threshold_is_not_reported_as_absent(self):
        analysis = analyze_trend(fetched([round(100 * 1.05 **i) for i in range(24)]),
                                 criterion={"min_monthly_views": 1_000_000})
        metric = analysis["metrics"][0]
        self.assertEqual(metric["metrics"]["agreement"], "sustained_growth")
        self.assertEqual(metric["criterion_evaluation"]["status"], "not_met")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for language in ("uk", "en"):
                with self.subTest(language=language):
                    expected = LABELS[language]["growth_below_criterion"].format(languages="uk")
                    self.assertEqual(_recommendation(analysis["metrics"], LABELS[language]), expected)
                    report_pdf(analysis, root / "chart.png", root / "report.pdf", language)
                    document = pdfium.PdfDocument(str(root / "report.pdf"))
                    try:
                        content = document[0].get_textpage().get_text_range()
                        self.assertIn(" ".join(expected.split()), " ".join(content.split()))
                        self.assertNotIn(LABELS[language]["no_growth"], content)
                    finally:
                        document.close()

    def test_pdf_and_chart_use_analyzed_metrics_and_show_sources(self):
        values = [100] * 12 + [130] * 11 + [1000]
        raw = fetched(values)
        raw["request"]["topic"] = "Астрономія"
        raw["resolved_pages"][0]["title"] = "Астрономія"
        raw["series"][0]["title"] = "Астрономія"
        analysis = analyze_trend(raw, exclusions={"uk": {"date": "2024-12-01", "reason": "разовий пік"}})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chart, report = root / "chart.png", root / "report.pdf"
            result = report_pdf(analysis, chart, report)
            self.assertEqual(result["pages"], 1)
            self.assertEqual(result["languages"], ["uk"])
            with Image.open(chart) as image:
                self.assertEqual(image.size, (1600, 650))
            document = pdfium.PdfDocument(str(report))
            self.assertEqual(len(document), 1)
            content = document[0].get_textpage().get_text_range()
            self.assertIn("Астрономія", content)
            self.assertIn("2023-01-01–2023-12-01", content)
            self.assertIn("Стійкий тренд", content)
            self.assertIn("https://example.test/api", content)
            self.assertIn("разовий пік", content)
            self.assertIn("2024-12-01", content)
            expected = analysis["metrics"][0]["metrics"]["comparison"]["percent_change"]
            self.assertIn(f"{expected:+.1f}%", content)
            self.assertGreaterEqual(report.read_bytes().count(b"/Subtype /Link"), 2)
            document.close()

    def test_visuals_reject_unanalyzed_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "analyzed JSON"):
                plot_chart(fetched([100] * 24), root / "chart.png")
            with self.assertRaisesRegex(ValueError, "analyzed JSON"):
                report_pdf(fetched([100] * 24), root / "chart.png", root / "report.pdf")


if __name__ == "__main__":
    unittest.main()
