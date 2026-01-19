"""Test field name normalization functionality."""

import unittest

from app.core.summary_contract import validate_and_shape_summary


class TestFieldNormalization(unittest.TestCase):
    """Test field name normalization from camelCase to snake_case."""

    def test_camelcase_to_snake_case_normalization(self) -> None:
        """Test that camelCase field names are normalized to snake_case."""
        # Test payload with camelCase field names (like in the error log)
        payload = {
            "summary250": "No source content provided; unable to generate a factual summary.",
            "summary1000": "No source text was provided. This response returns the required JSON schema with placeholders or empty fields where appropriate; summaries, ideas, entities, stats, and questions cannot be derived without content.",
            "keyideas": [
                "no source content",
                "summary unavailable",
                "entities not provided",
                "statistics unavailable",
                "placeholders used",
            ],
            "topictags": ["no content", "summary", "placeholder", "metadata", "schema", "json"],
            "entities": {"people": [], "organizations": [], "locations": []},
            "estimatedreadingtimemin": 0,
            "keystats": [],
            "answeredquestions": [],
            "readability": {"method": "Flesch-Kincaid", "score": 0, "level": "unknown"},
            "seokeywords": [
                "no content",
                "missing data",
                "summary",
                "json schema",
                "placeholder",
                "metadata",
                "error handling",
            ],
        }

        result = validate_and_shape_summary(payload)

        # Check that the normalized fields exist
        assert "summary_250" in result
        assert "summary_1000" in result
        assert "tldr" in result
        assert "key_ideas" in result
        assert "topic_tags" in result
        assert "estimated_reading_time_min" in result
        assert "key_stats" in result
        assert "answered_questions" in result
        assert "seo_keywords" in result

        # Check that the content was preserved
        assert (
            result["summary_250"]
            == "No source content provided; unable to generate a factual summary."
        )
        assert result["summary_1000"] == payload["summary1000"]
        assert len(result["key_ideas"]) == 5
        assert len(result["topic_tags"]) == 6
        assert result["estimated_reading_time_min"] == 0

    def test_mixed_case_field_names(self) -> None:
        """Test normalization of mixed case field names."""
        payload = {
            "summary250": "Test summary 250",
            "keyIdeas": ["idea1", "idea2"],
            "topicTags": ["tag1", "tag2"],
            "estimatedReadingTimeMin": 5,
            "keyStats": [],
            "answeredQuestions": [],
            "seoKeywords": ["keyword1", "keyword2"],
            "entities": {"people": [], "organizations": [], "locations": []},
            "readability": {"method": "test", "score": 50, "level": "easy"},
        }

        result = validate_and_shape_summary(payload)

        # Check that all fields are normalized
        assert "summary_250" in result
        assert "key_ideas" in result
        assert "topic_tags" in result
        assert "estimated_reading_time_min" in result
        assert "key_stats" in result
        assert "answered_questions" in result
        assert "seo_keywords" in result

        # Check content preservation
        assert result["summary_250"] == "Test summary 250"
        assert result["summary_1000"] == "Test summary 250"
        assert result["key_ideas"] == ["idea1", "idea2"]
        assert result["topic_tags"] == ["#tag1", "#tag2"]  # Should be hash-tagged
        assert result["estimated_reading_time_min"] == 5

    def test_already_correct_field_names(self) -> None:
        """Test that already correct snake_case field names are preserved."""
        payload = {
            "summary_250": "Test summary 250",
            "summary_1000": "Test summary 1000",
            "key_ideas": ["idea1", "idea2"],
            "topic_tags": ["tag1", "tag2"],
            "estimated_reading_time_min": 5,
            "key_stats": [],
            "answered_questions": [],
            "seo_keywords": ["keyword1", "keyword2"],
            "entities": {"people": [], "organizations": [], "locations": []},
            "readability": {"method": "test", "score": 50, "level": "easy"},
        }

        result = validate_and_shape_summary(payload)

        # Check that all fields are preserved
        assert "summary_250" in result
        assert "summary_1000" in result
        assert "tldr" in result
        assert "key_ideas" in result
        assert "topic_tags" in result
        assert "estimated_reading_time_min" in result
        assert "key_stats" in result
        assert "answered_questions" in result
        assert "seo_keywords" in result

        # Check content preservation
        assert result["summary_250"] == "Test summary 250"
        assert result["summary_1000"] == "Test summary 1000"
        # Note: tldr is intentionally enriched with key_ideas when it equals summary_1000
        # This is expected behavior per the summary contract
        assert "Test summary 1000" in result["tldr"]
        assert "Key ideas" in result["tldr"]  # tldr should be enriched
        assert result["key_ideas"] == ["idea1", "idea2"]


if __name__ == "__main__":
    unittest.main()
