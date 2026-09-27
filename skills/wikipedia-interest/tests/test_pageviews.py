import io
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from wikipedia_interest.pageviews import (PageviewsClient, PageviewsError, _api_url, _cache_key,
                                          _chunks, _same_title, _validated_dates, fetch_pageviews)


RESOLVED = {
    "status": "resolved",
    "resolved_pages": [{"language": "uk", "project": "uk.wikipedia.org", "title": "Астрономія",
                        "url": "https://uk.wikipedia.org/wiki/Астрономія", "status": "selected",
                        "warnings": []}],
}


class FakeClient:
    def __init__(self, months=None, fail=False):
        self.months = months or {}
        self.calls = []
        self.fail = fail

    def fetch(self, url):
        self.calls.append(url)
        if self.fail:
            raise PageviewsError("API unavailable")
        return {"items": [
            {"project": "uk.wikipedia", "article": "Астрономія",
             "access": "all-access", "agent": "user", "granularity": "monthly",
             "timestamp": month + "00", "views": count}
            for month, count in self.months.items()
        ]}


class PageviewsTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 27)
        self.now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)

    def test_url_encodes_title_and_cache_key_includes_metric(self):
        url = _api_url("uk.wikipedia.org", "Теорія відносності/історія", "all-access", "user",
                       "monthly", date(2024, 1, 1), date(2024, 12, 31))
        self.assertIn("%2F", url)
        self.assertIn("%D0%A2", url)
        one = _cache_key("uk.wikipedia.org", "Астрономія", "all-access", "user",
                         "monthly", date(2024, 1, 1), date(2024, 12, 31))
        two = _cache_key("uk.wikipedia.org", "Астрономія", "desktop", "user",
                         "monthly", date(2024, 1, 1), date(2024, 12, 31))
        self.assertNotEqual(one, two)

    def test_date_bounds_and_unicode_title_normalization(self):
        self.assertEqual(_validated_dates("2024-01-15", "2024-02-20", self.today),
                         (date(2024, 1, 15), date(2024, 2, 20)))
        for start, end in (("2015-06-30", "2015-07-01"),
                           ("2024-03-01", "2024-02-29"),
                           ("2026-09-28", "2026-09-28"),
                           ("2024-13-01", "2024-12-31")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                _validated_dates(start, end, self.today)
        self.assertTrue(_same_title("Café_au_lait", "Cafe\u0301 au lait"))
        self.assertFalse(_same_title("Astronomy", "Astrology"))

    def test_reuses_complete_chunk_for_changed_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient({"20240101": 10, "20240201": 20})
            first = fetch_pageviews(RESOLVED, start="2024-01-15", end="2024-02-20",
                                    cache_dir=Path(temp), client=client,
                                    today=self.today, now=self.now)
            second = fetch_pageviews(RESOLVED, start="2024-02-01", end="2024-02-29",
                                     cache_dir=Path(temp), client=client,
                                     today=self.today, now=self.now)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual([point["views"] for point in first["series"][0]["points"]], [10, 20])
            self.assertEqual([point["date"] for point in second["series"][0]["points"]], ["2024-02-01"])
            self.assertEqual(second["cache"]["hits"], 1)
            self.assertEqual(len(list((Path(temp) / "raw").glob("*.json"))), 1)
            self.assertEqual(len(list((Path(temp) / "normalized").glob("*.json"))), 1)

    def test_missing_point_is_null_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            result = fetch_pageviews(RESOLVED, start="2024-01-01", end="2024-03-31",
                                     cache_dir=Path(temp), client=FakeClient({"20240101": 12}),
                                     today=self.today, now=self.now)
            self.assertEqual(result["status"], "partial")
            self.assertEqual([p["views"] for p in result["series"][0]["points"]], [12, None, None])
            self.assertIn("missing_points", result["quality_flags"])

    def test_current_month_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            result = fetch_pageviews(RESOLVED, start="2026-09-01", end="2026-09-27",
                                     cache_dir=Path(temp), client=FakeClient({"20260901": 5}),
                                     today=self.today, now=self.now)
            self.assertEqual(result["status"], "partial")
            self.assertFalse(result["series"][0]["points"][0]["complete"])
            self.assertIn("incomplete_period", result["quality_flags"])

    def test_daily_missing_and_current_day(self):
        class DailyClient:
            def fetch(self, url):
                return {"items": [{"project": "uk.wikipedia", "article": "Астрономія",
                                   "access": "all-access", "agent": "user", "granularity": "daily",
                                   "timestamp": "2026092500", "views": 7}]}

        with tempfile.TemporaryDirectory() as temp:
            result = fetch_pageviews(RESOLVED, start="2026-09-25", end="2026-09-27",
                                     cache_dir=Path(temp), client=DailyClient(),
                                     granularity="daily", today=self.today, now=self.now)
            points = result["series"][0]["points"]
            self.assertEqual([point["views"] for point in points], [7, None, None])
            self.assertTrue(points[1]["complete"])
            self.assertFalse(points[2]["complete"])

    def test_past_daily_request_avoids_current_day_chunk(self):
        chunks = list(_chunks(date(2026, 9, 10), date(2026, 9, 12), "daily", self.today))
        self.assertEqual(chunks, [(date(2026, 9, 1), date(2026, 9, 26), False)])

    def test_api_title_difference_is_flagged(self):
        class RenamedClient(FakeClient):
            def fetch(self, url):
                payload = super().fetch(url)
                payload["items"][0]["article"] = "Інша назва"
                return payload

        with tempfile.TemporaryDirectory() as temp:
            result = fetch_pageviews(RESOLVED, start="2024-01-01", end="2024-01-31",
                                     cache_dir=Path(temp), client=RenamedClient({"20240101": 1}),
                                     today=self.today, now=self.now)
            self.assertIn("api_article_title_differs", result["quality_flags"])

    def test_api_failure_does_not_return_series(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(PageviewsError, "API unavailable"):
                fetch_pageviews(RESOLVED, start="2024-01-01", end="2024-01-31",
                                cache_dir=Path(temp), client=FakeClient(fail=True),
                                today=self.today, now=self.now)

    def test_rejects_unconfirmed_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "status 'resolved'"):
                fetch_pageviews({"status": "needs_confirmation"}, start="2024-01-01",
                                end="2024-02-01", cache_dir=Path(temp), client=FakeClient(),
                                today=self.today, now=self.now)

    def test_retry_is_bounded_for_transient_http_error(self):
        error = urllib.error.HTTPError("https://example.test", 503, "busy", None, None)
        try:
            with patch("urllib.request.urlopen", side_effect=[error, io.BytesIO(b'{"items": []}')]) as opener:
                with patch("time.sleep") as sleeper:
                    result = PageviewsClient("test@example.org").fetch("https://example.test")
        finally:
            error.close()
        self.assertEqual(result, {"items": []})
        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once()


if __name__ == "__main__":
    unittest.main()
