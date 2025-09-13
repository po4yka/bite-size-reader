import unittest

from app.core.summary_contract import validate_and_shape_summary


class TestSummaryContract(unittest.TestCase):
    def test_caps_and_tags_and_entities(self):
        payload = {
            "summary_250": "A" * 400 + " end.",
            "summary_1000": "B" * 1200 + " end.",
            "key_ideas": [" idea1 ", "", "idea2"],
            "topic_tags": ["tag1", "#Tag1", "tag2"],
            "entities": {
                "people": ["Alice", "alice", "Bob"],
                "organizations": ["ACME", "acme"],
                "locations": ["NY", "ny"],
            },
            "estimated_reading_time_min": "7",
        }

        out = validate_and_shape_summary(payload)

        self.assertLessEqual(len(out["summary_250"]), 250)
        self.assertLessEqual(len(out["summary_1000"]), 1000)
        self.assertEqual(out["topic_tags"], ["#tag1", "#tag2"])  # dedup + hash prefix
        self.assertEqual(out["entities"]["people"], ["Alice", "Bob"])  # dedup case-insensitive
        self.assertEqual(out["estimated_reading_time_min"], 7)
        self.assertIn("key_stats", out)
        self.assertIn("readability", out)


if __name__ == "__main__":
    unittest.main()

