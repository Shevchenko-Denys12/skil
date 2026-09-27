import copy
import unittest

from wikipedia_interest.analysis import _agreement, analyze_trend


def fetched(values, *, language="uk"):
    points = []
    for index, value in enumerate(values):
        year = 2023 + index // 12
        month = index % 12 + 1
        points.append({"date": f"{year:04d}-{month:02d}-01", "views": value,
                       "complete": True, "missing": value is None})
    return {
        "status": "partial" if None in values else "ok",
        "request": {"start": points[0]["date"], "end": points[-1]["date"],
                    "access": "all-access", "agent": "user", "granularity": "monthly"},
        "resolved_pages": [{"language": language, "project": f"{language}.wikipedia.org",
                            "title": "Test", "url": "https://example.test", "status": "selected"}],
        "series": [{"language": language, "project": f"{language}.wikipedia.org",
                    "title": "Test", "url": "https://example.test", "access": "all-access",
                    "agent": "user", "granularity": "monthly",
                    "requested_start": points[0]["date"], "requested_end": points[-1]["date"],
                    "points": points, "quality_flags": [], "sources": ["https://example.test/api"]}],
        "sources": ["https://example.test/api"],
        "cache": {"hits": 1, "misses": 0},
    }


def metric(result):
    return result["metrics"][0]


class AnalysisTests(unittest.TestCase):
    def test_sustained_growth_has_two_positive_signals(self):
        result = analyze_trend(fetched([round(100 * 1.05 ** index) for index in range(24)]))
        item = metric(result)
        self.assertEqual(item["metrics"]["agreement"], "sustained_growth")
        self.assertGreater(item["metrics"]["comparison"]["percent_change"], 15)
        self.assertGreater(item["metrics"]["robust_trend"]["percent_change_over_span"], 15)
        self.assertEqual(item["reliability"]["level"], "вища")

    def test_zero_baseline_has_no_percentage_or_confident_direction(self):
        item = metric(analyze_trend(fetched([0] * 12 + [50] * 12)))
        self.assertIsNone(item["metrics"]["comparison"]["percent_change"])
        self.assertEqual(item["metrics"]["agreement"], "uncertain")
        self.assertIn("zero_baseline", item["quality_flags"])
        self.assertIn("low_volume", item["quality_flags"])

    def test_missing_month_blocks_signals_without_interpolation(self):
        values = [100] * 24
        values[18] = None
        item = metric(analyze_trend(fetched(values)))
        self.assertIsNone(item["metrics"]["comparison"]["percent_change"])
        self.assertIsNone(item["metrics"]["robust_trend"]["percent_change_over_span"])
        self.assertIn("missing_points", item["quality_flags"])
        self.assertEqual(item["reliability"]["level"], "низька")

    def test_repeated_seasonal_pattern_is_flagged(self):
        seasonal = [200, 180, 150, 100, 80, 60, 50, 60, 100, 150, 180, 200]
        item = metric(analyze_trend(fetched(seasonal * 2)))
        self.assertIn("possible_seasonality", item["quality_flags"])
        self.assertEqual(item["metrics"]["comparison"]["percent_change"], 0.0)

    def test_spike_exclusion_recomputes_both_signals_and_keeps_original(self):
        values = [100] * 23 + [1000]
        result = analyze_trend(fetched(values), exclusions={"uk": {"date": "2024-12-01",
                                                              "reason": "one-off event"}})
        original = result["metrics"][0]
        alternative = result["alternatives"][0]
        alternate_metrics = alternative["analysis"]["metrics"]
        self.assertEqual(original["metrics"]["agreement"], "uncertain")
        self.assertIn("strong_spike", original["quality_flags"])
        self.assertEqual(alternate_metrics["agreement"], "no_convincing_change")
        self.assertEqual(alternate_metrics["comparison"]["percent_change"], 0.0)
        self.assertEqual(alternate_metrics["robust_trend"]["percent_change_over_span"], 0.0)
        self.assertEqual(alternate_metrics["comparison"]["paired_excluded_date"], "2023-12-01")
        self.assertTrue(alternative["conclusion_changed"])
        self.assertEqual(alternative["reason"], "one-off event")

    def test_short_series_uses_equal_six_month_periods(self):
        item = metric(analyze_trend(fetched([100] * 6 + [120] * 6)))
        self.assertEqual(item["metrics"]["comparison"]["months_per_period"], 6)
        self.assertIn("short_history", item["quality_flags"])

    def test_too_short_series_is_uncertain(self):
        item = metric(analyze_trend(fetched([100] * 11)))
        self.assertIsNone(item["metrics"]["comparison"]["percent_change"])
        self.assertIsNone(item["metrics"]["robust_trend"]["percent_change_over_span"])
        self.assertIn("too_few_points", item["quality_flags"])

    def test_criterion_is_separate_from_trend(self):
        series = fetched([100] * 24)
        plain = analyze_trend(series)
        assessed = analyze_trend(series, criterion={"min_monthly_views": 150,
                                                     "min_period_change_pct": 10})
        self.assertEqual(metric(plain)["metrics"], metric(assessed)["metrics"])
        self.assertEqual(metric(assessed)["criterion_evaluation"]["status"], "not_met")

    def test_identical_input_is_deterministic(self):
        series = fetched([100] * 12 + [130] * 12)
        self.assertEqual(analyze_trend(series), analyze_trend(copy.deepcopy(series)))

    def test_conflicting_signal_rule_is_uncertain(self):
        self.assertEqual(_agreement(25.0, -20.0), "uncertain")
        self.assertEqual(_agreement(2.0, -3.0), "no_convincing_change")

    def test_incomplete_current_month_is_excluded(self):
        series = fetched([100] * 24)
        series["series"][0]["points"].append({"date": "2025-01-01", "views": 1000,
                                                "complete": False, "missing": False})
        item = metric(analyze_trend(series))
        self.assertEqual(item["metrics"]["analysis_end"], "2024-12-01")
        self.assertIn("incomplete_period", item["quality_flags"])

    def test_rejects_mixed_metric_definitions_and_dates(self):
        series = fetched([100] * 24)
        other = copy.deepcopy(series["series"][0])
        other["language"] = "pl"
        other["project"] = "pl.wikipedia.org"
        other["agent"] = "all-agents"
        series["series"].append(other)
        with self.assertRaisesRegex(ValueError, "same access"):
            analyze_trend(series)
        other["agent"] = "user"
        other["points"][-1]["date"] = "2025-01-01"
        with self.assertRaises(ValueError):
            analyze_trend(series)

    def test_language_comparison_keeps_dynamics_and_scale_separate(self):
        series = fetched([100] * 24)
        other = copy.deepcopy(fetched([200] * 24, language="pl"))
        series["series"].extend(other["series"])
        series["resolved_pages"].extend(other["resolved_pages"])
        result = analyze_trend(series)
        comparison = result["language_comparison"]
        self.assertEqual([row["period_change_pct"] for row in comparison["dynamics"]], [0.0, 0.0])
        self.assertEqual([row["mean_monthly_views"] for row in comparison["scale"]], [100.0, 200.0])


if __name__ == "__main__":
    unittest.main()
