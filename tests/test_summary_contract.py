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

    def test_entities_handles_list_payloads(self):
        payload = {
            "summary_250": "Short summary.",
            "summary_1000": "Longer summary that provides more detail.",
            "entities": [
                {
                    "type": "people",
                    "entities": ["Alice", {"name": "Bob"}],
                },
                {
                    "type": "organization",
                    "names": ["OpenAI", "Anthropic"],
                },
                {
                    "label": "locations",
                    "values": ["San Francisco", "New York"],
                },
                "Charlie",
            ],
        }

        out = validate_and_shape_summary(payload)

        self.assertEqual(out["entities"]["people"], ["Alice", "Bob", "Charlie"])
        self.assertEqual(out["entities"]["organizations"], ["OpenAI", "Anthropic"])
        self.assertEqual(out["entities"]["locations"], ["San Francisco", "New York"])


if __name__ == "__main__":
    unittest.main()
