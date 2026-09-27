import tempfile
import unittest
from pathlib import Path

from wikipedia_interest.environment import SKILL_ROOT, check_environment


class EnvironmentTests(unittest.TestCase):
    def test_creates_external_work_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = check_environment(root / "cache", root / "artifacts")
            self.assertEqual(result["status"], "ready")
            self.assertTrue((root / "cache").is_dir())
            self.assertTrue((root / "artifacts").is_dir())
            self.assertTrue(result["capabilities"]["article_resolution"])
            self.assertTrue(result["capabilities"]["pageviews_fetch"])
            self.assertTrue(result["capabilities"]["trend_analysis"])
            self.assertEqual(result["stage"], 7)
            self.assertTrue(result["capabilities"]["chart"])
            self.assertTrue(result["capabilities"]["pdf_report"])
            self.assertTrue(result["capabilities"]["one_command_workflow"])

    def test_rejects_source_tree_as_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "outside the skill directory"):
                check_environment(SKILL_ROOT / "cache", Path(temp) / "artifacts")

    def test_rejects_same_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "must differ"):
                check_environment(Path(temp), Path(temp))


if __name__ == "__main__":
    unittest.main()
