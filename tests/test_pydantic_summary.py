import unittest

from app.core.summary_contract import validate_and_shape_summary
from app.core.summary_schema import PydanticAvailable


@unittest.skipUnless(PydanticAvailable, "Pydantic not available")
class TestPydanticSummary(unittest.TestCase):
    def test_summarymodel_rejects_overlong(self):
        from pydantic import ValidationError

        from app.core.summary_schema import SummaryModel

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

        with self.assertRaises(ValidationError):
            SummaryModel(**payload)

    def test_validate_and_shape_is_model_compatible(self):
        from app.core.summary_schema import SummaryModel

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
        self.assertLessEqual(len(shaped["summary_250"]), 250)
        self.assertLessEqual(len(shaped["summary_1000"]), 1000)
        self.assertEqual(shaped["topic_tags"], ["#tag"])  # dedup
        self.assertEqual(shaped["entities"]["people"], ["A"])  # dedup case-insensitive
        # Should be valid per pydantic model
        model = SummaryModel(**shaped)
        dumped = model.model_dump()
        # spot check a few fields
        self.assertIn("summary_250", dumped)
        self.assertIn("summary_1000", dumped)
        self.assertIn("tldr", dumped)
        self.assertIn("entities", dumped)
        self.assertIsInstance(dumped["estimated_reading_time_min"], int)


if __name__ == "__main__":
    unittest.main()
