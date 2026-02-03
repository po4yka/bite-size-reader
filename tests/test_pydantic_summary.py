import unittest

from app.core.summary_contract import validate_and_shape_summary
from app.core.summary_schema import SummaryModel


class TestPydanticSummary(unittest.TestCase):
    def test_summarymodel_caps_overlong(self):
        """SummaryModel field validators cap overlong summaries instead of rejecting."""
        payload = {
            "summary_250": "x" * 300,
            "summary_1000": "y" * 1200,
            "tldr": "y" * 1200,
            "key_ideas": [],
            "topic_tags": [],
            "entities": {"people": [], "organizations": [], "locations": []},
            "estimated_reading_time_min": 0,
            "key_stats": [],
            "answered_questions": [],
            "readability": {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"},
            "seo_keywords": [],
        }

        model = SummaryModel(**payload)
        assert len(model.summary_250) <= 250
        assert len(model.summary_1000) <= 1000

    def test_validate_and_shape_is_model_compatible(self):
        payload = {
            "summary_250": "x" * 300,
            "summary_1000": "ok",
            "tldr": "ok",
            "key_ideas": ["a", "b"],
            "topic_tags": ["tag", "#tag"],
            "entities": {"people": ["A", "a"], "organizations": [], "locations": []},
            "estimated_reading_time_min": "5",
            "key_stats": [
                {"label": "Market size", "value": "12.3", "unit": "BUSD"},
                {"label": "bad", "value": "n/a"},
            ],
            "answered_questions": ["What?"],
            "readability": {"score": "not-a-number"},
            "seo_keywords": ["k1"],
        }

        shaped = validate_and_shape_summary(payload)
        # Should respect caps and dedupe
        assert len(shaped["summary_250"]) <= 250
        assert len(shaped["summary_1000"]) <= 1000
        assert shaped["topic_tags"] == ["#tag"]  # dedup
        assert shaped["entities"]["people"] == ["A"]  # dedup case-insensitive
        # Should be valid per pydantic model
        model = SummaryModel(**shaped)
        dumped = model.model_dump()
        # spot check a few fields
        assert "summary_250" in dumped
        assert "summary_1000" in dumped
        assert "tldr" in dumped
        assert "entities" in dumped
        assert isinstance(dumped["estimated_reading_time_min"], int)


if __name__ == "__main__":
    unittest.main()
