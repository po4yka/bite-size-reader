import unittest

from app.core.summary_contract import validate_and_shape_summary


class TestSummaryContract(unittest.TestCase):
    def test_caps_and_tags_and_entities(self):
        payload = {
            "summary_250": "A" * 400 + " end.",
            "summary_1000": "B" * 1200 + " end.",
            "tldr": "C" * 1400 + " end.",
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

        assert len(out["summary_250"]) <= 250
        assert len(out["summary_1000"]) <= 1000
        assert out["tldr"].startswith("C" * 100)
        assert out["topic_tags"] == ["#tag1", "#tag2"]  # dedup + hash prefix
        assert out["entities"]["people"] == ["Alice", "Bob"]  # dedup case-insensitive
        assert out["estimated_reading_time_min"] == 7
        assert "key_stats" in out
        assert "readability" in out

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

        assert out["summary_1000"] == "Longer summary that provides more detail."
        assert out["tldr"] == "Longer summary that provides more detail."
        assert out["entities"]["people"] == ["Alice", "Bob", "Charlie"]
        assert out["entities"]["organizations"] == ["OpenAI", "Anthropic"]
        assert out["entities"]["locations"] == ["San Francisco", "New York"]

    def test_fallback_summary_from_supporting_fields(self):
        payload = {
            "key_ideas": [
                "Key idea one highlights the main vulnerability.",
                "Key idea two explains the mitigation steps.",
            ],
            "highlights": ["Highlight content adds additional context."],
            "insights": {"topic_overview": "Overall, the article explores safety bypasses."},
        }

        out = validate_and_shape_summary(payload)

        assert out["summary_250"].strip()
        assert out["summary_1000"].strip()
        assert out["tldr"].strip()
        assert "Key idea one" in out["summary_1000"]


if __name__ == "__main__":
    unittest.main()
