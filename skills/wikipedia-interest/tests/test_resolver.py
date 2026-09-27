import unittest

from wikipedia_interest.resolver import MediaWikiClient, parse_page_input, resolve_topic


def page(title, links=None, *, disambiguation=False, redirect=None):
    return {
        "title": title,
        "url": "https://example.test/wiki/" + title.replace(" ", "_"),
        "namespace": 0,
        "disambiguation": disambiguation,
        "redirected_from": redirect,
        "langlinks": links or {},
    }


class FakeClient:
    def __init__(self, pages=None, searches=None):
        self.pages = pages or {}
        self.searches = searches or {}

    def page(self, language, title):
        return self.pages.get((language, title))

    def search(self, language, phrase):
        return self.searches.get((language, phrase), [])


class ResolverTests(unittest.TestCase):
    def test_exact_seed_uses_verified_interlanguage_links(self):
        client = FakeClient({
            ("en", "Intermittent fasting"): page("Intermittent fasting", {"pl": "Post przerywany", "cs": "Přerušovaný půst"}),
            ("pl", "Post przerywany"): page("Post przerywany"),
            ("cs", "Přerušovaný půst"): page("Přerušovaný půst"),
        })
        result = resolve_topic(client, "Intermittent fasting", ["pl", "cs"])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual([row["match_method"] for row in result["resolved_pages"]],
                         ["interlanguage_link", "interlanguage_link"])

    def test_search_result_is_not_silently_confirmed(self):
        client = FakeClient(
            {("en", "Mercury (planet)"): page("Mercury (planet)", {"uk": "Меркурій (планета)"}),
             ("uk", "Меркурій (планета)"): page("Меркурій (планета)")},
            {("en", "Mercury topic"): ["Mercury (planet)", "Mercury (element)"]},
        )
        result = resolve_topic(client, "Mercury topic", ["uk"])
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["resolved_pages"][0]["status"], "needs_confirmation")
        self.assertIn("unconfirmed_search_seed", result["resolved_pages"][0]["warnings"])

    def test_missing_link_does_not_offer_unrelated_text_matches(self):
        client = FakeClient(
            {("en", "Astronomy"): page("Astronomy")},
            {("uk", "Astronomy"): ["Астрономія", "Історія астрономії"]},
        )
        result = resolve_topic(client, "Astronomy", ["uk"])
        row = result["resolved_pages"][0]
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["candidates"], [])
        self.assertIn("no_verified_interlanguage_match", row["warnings"])

    def test_explicit_page_redirect_and_semantic_mismatch_are_visible(self):
        client = FakeClient({
            ("pl", "Post"): page("Post przerywany", {"cs": "Přerušovaný půst"}, redirect="Post"),
            ("cs", "Půst"): page("Půst"),
        })
        result = resolve_topic(client, None, ["pl", "cs"], {"pl": "Post", "cs": "Půst"})
        self.assertEqual(result["status"], "resolved")
        self.assertIn("semantic_mismatch_with_seed_langlink", result["resolved_pages"][1]["warnings"])
        self.assertIn("redirected_from:Post", result["resolved_pages"][0]["warnings"])

    def test_disambiguation_requires_confirmation(self):
        client = FakeClient({("en", "Mercury"): page("Mercury", disambiguation=True)})
        result = resolve_topic(client, "Mercury", ["en"])
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("disambiguation_page", result["resolved_pages"][0]["warnings"])

    def test_url_language_and_title_validation(self):
        self.assertEqual(parse_page_input("uk", "https://uk.wikipedia.org/wiki/%D0%90%D1%81%D1%82%D1%80%D0%BE%D0%BD%D0%BE%D0%BC%D1%96%D1%8F"), "Астрономія")
        with self.assertRaises(ValueError):
            parse_page_input("uk", "https://en.wikipedia.org/wiki/Astronomy")
        with self.assertRaises(ValueError):
            resolve_topic(FakeClient(), "topic", ["en", "en"])


class ApiParsingTests(unittest.TestCase):
    def test_page_follows_continuation_and_redirect(self):
        class StubClient(MediaWikiClient):
            def __init__(self):
                self.calls = 0

            def query(self, language, **params):
                self.calls += 1
                base = {"query": {"pages": [{"title": "New", "ns": 0, "fullurl": "https://en.wikipedia.org/wiki/New",
                                              "pageprops": {}, "langlinks": [{"lang": "pl", "title": "Nowy"}]}]}}
                if self.calls == 1:
                    base["query"]["redirects"] = [{"from": "Old", "to": "New"}]
                    base["continue"] = {"llcontinue": "123|pl", "continue": "||"}
                else:
                    base["query"]["pages"][0]["langlinks"] = [{"lang": "cs", "title": "Nový"}]
                return base

        result = StubClient().page("en", "Old")
        self.assertEqual(result["title"], "New")
        self.assertEqual(result["redirected_from"], "Old")
        self.assertEqual(result["langlinks"], {"pl": "Nowy", "cs": "Nový"})


if __name__ == "__main__":
    unittest.main()
