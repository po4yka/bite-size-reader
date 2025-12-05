"""Unit tests for ValidationAgent."""

import unittest
from unittest.mock import patch

from app.agents.validation_agent import ValidationAgent, ValidationInput  # Corrected import


class TestValidationAgent(unittest.IsolatedAsyncioTestCase):
    """Test ValidationAgent functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.correlation_id = "validation-test-123"
        self.agent = ValidationAgent(correlation_id=self.correlation_id)

        # Valid summary example
        self.valid_summary = {
            "summary_250": "Short summary under 250 characters.",
            "summary_1000": "Longer summary with multiple sentences that provides more detail but stays under 1000 characters.",
            "tldr": "TLDR summary",
            "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
            "topic_tags": ["#tech", "#ai", "#innovation"],
            "entities": {
                "people": ["John Doe"],
                "organizations": ["OpenAI"],
                "locations": ["San Francisco"],
            },
            "estimated_reading_time_min": 5,
            "key_stats": [
                {
                    "label": "Market Cap",
                    "value": 100.5,
                    "unit": "billion USD",
                    "source_excerpt": "Market cap is $100.5B",
                }
            ],
            "answered_questions": ["What is AI?", "How does it work?"],
            "readability": {"method": "Flesch-Kincaid", "score": 12.0, "level": "College"},
            "seo_keywords": ["artificial intelligence", "machine learning", "technology"],
        }

    async def test_valid_summary_passes_validation(self):
        """Test that a valid summary passes all validation checks."""
        input_data = ValidationInput(summary_json=self.valid_summary)

        with patch("app.agents.validation_agent.validate_and_shape_summary") as mock_validate:
            mock_validate.return_value = self.valid_summary
            result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.output)
        self.assertEqual(result.output.summary_json, self.valid_summary)
        self.assertIsNone(result.error)

    async def test_missing_required_fields_fails(self):
        """Test validation fails when required fields are missing."""
        incomplete_summary = {
            "summary_250": "Short summary",
            "tldr": "TLDR",
            # Missing most required fields
        }
        input_data = ValidationInput(summary_json=incomplete_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("Missing required fields", result.error)
        self.assertIn("summary_1000", result.error)
        self.assertIn("key_ideas", result.error)

    async def test_summary_250_character_limit_violation(self):
        """Test validation fails when summary_250 exceeds character limit."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["summary_250"] = "X" * 300  # Exceeds 250 char limit
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("summary_250 exceeds limit", result.error)
        self.assertIn("300 chars", result.error)
        self.assertIn("max 250", result.error)

    async def test_summary_1000_character_limit_violation(self):
        """Test validation fails when summary_1000 exceeds character limit."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["summary_1000"] = "Y" * 1100  # Exceeds 1000 char limit
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("summary_1000 exceeds limit", result.error)
        self.assertIn("1100 chars", result.error)
        self.assertIn("max 1000", result.error)

    async def test_topic_tags_missing_hash_prefix(self):
        """Test validation fails when topic tags don't have # prefix."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["topic_tags"] = ["#valid", "invalid", "also_invalid"]
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("Topic tags missing '#' prefix", result.error)
        self.assertIn("invalid", result.error)
        self.assertIn("also_invalid", result.error)

    async def test_topic_tags_not_list_fails(self):
        """Test validation fails when topic_tags is not a list."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["topic_tags"] = "#single_tag"  # String instead of list
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("topic_tags must be a list", result.error)

    async def test_entities_not_dict_fails(self):
        """Test validation fails when entities is not a dictionary."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["entities"] = ["not", "a", "dict"]
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("entities must be a dictionary", result.error)

    async def test_entities_missing_required_types(self):
        """Test validation fails when entities is missing required types."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["entities"] = {
            "people": ["John Doe"],
            # Missing organizations and locations
        }
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("entities.organizations is required", result.error)
        self.assertIn("entities.locations is required", result.error)

    async def test_entities_type_not_list_fails(self):
        """Test validation fails when entity type is not a list."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["entities"]["people"] = "John Doe"  # String instead of list
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("entities.people must be a list", result.error)

    async def test_key_stats_not_list_fails(self):
        """Test validation fails when key_stats is not a list."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["key_stats"] = "not a list"
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("key_stats must be a list", result.error)

    async def test_key_stats_missing_required_fields(self):
        """Test validation fails when key_stats items missing required fields."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["key_stats"] = [
            {"label": "Stat", "value": 42},  # Valid
            {"label": "Missing value"},  # Invalid - no value
            {"value": 100},  # Invalid - no label
        ]
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("key_stats[1] missing 'value' field", result.error)
        self.assertIn("key_stats[2] missing 'label' field", result.error)

    async def test_key_stats_non_numeric_value_fails(self):
        """Test validation fails when key_stats value is not numeric."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["key_stats"] = [{"label": "Invalid", "value": "not a number"}]
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("key_stats[0].value must be numeric", result.error)

    async def test_readability_not_dict_fails(self):
        """Test validation fails when readability is not a dictionary."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["readability"] = "not a dict"
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("readability must be a dictionary", result.error)

    async def test_readability_missing_score_fails(self):
        """Test validation fails when readability is missing score."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["readability"] = {"level": "College"}  # Missing score
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("readability.score is required", result.error)

    async def test_readability_non_numeric_score_fails(self):
        """Test validation fails when readability score is not numeric."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["readability"] = {"score": "high", "level": "College"}
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("readability.score must be numeric", result.error)

    async def test_estimated_reading_time_not_int_fails(self):
        """Test validation fails when estimated_reading_time_min is not integer."""
        invalid_summary = self.valid_summary.copy()
        invalid_summary["estimated_reading_time_min"] = 5.5  # Float instead of int
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("estimated_reading_time_min must be integer", result.error)

    async def test_multiple_validation_errors_all_reported(self):
        """Test that multiple validation errors are all reported."""
        invalid_summary = {
            "summary_250": "X" * 300,  # Too long
            "summary_1000": "Y" * 50,  # Present but short (warning)
            "tldr": "TLDR",
            "key_ideas": ["idea1"],
            "topic_tags": ["#valid", "invalid"],  # Missing # on second tag
            # Missing entities, estimated_reading_time_min, etc.
        }
        input_data = ValidationInput(summary_json=invalid_summary)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("validation errors", result.error.lower())
        # Should contain multiple specific errors
        self.assertIn("summary_250 exceeds limit", result.error)
        self.assertIn("Topic tags missing '#' prefix", result.error)
        self.assertIn("Missing required fields", result.error)

    async def test_validation_warnings_included_in_success(self):
        """Test that validation warnings are included in successful results."""
        summary_with_warnings = self.valid_summary.copy()
        summary_with_warnings["summary_250"] = "Very short."  # Only 12 chars - warning
        summary_with_warnings["topic_tags"] = ["#" + str(i) for i in range(15)]  # 15 tags - warning
        input_data = ValidationInput(summary_json=summary_with_warnings)

        with patch("app.agents.validation_agent.validate_and_shape_summary") as mock_validate:
            mock_validate.return_value = summary_with_warnings
            result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.output)
        # Warnings should be in output
        self.assertGreater(len(result.output.validation_warnings), 0)

    async def test_contract_validation_exception_handled(self):
        """Test that exceptions from validate_and_shape_summary are handled."""
        input_data = ValidationInput(summary_json=self.valid_summary)

        with patch("app.agents.validation_agent.validate_and_shape_summary") as mock_validate:
            mock_validate.side_effect = ValueError("Contract validation failed")
            result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("Summary contract validation failed", result.error)
        self.assertIn("Contract validation failed", result.error)

    async def test_format_single_error(self):
        """Test formatting of a single validation error."""
        errors = ["Single error message"]
        formatted = self.agent._format_validation_errors(errors)

        self.assertEqual(formatted, "Single error message")

    async def test_format_multiple_errors(self):
        """Test formatting of multiple validation errors."""
        errors = ["Error 1", "Error 2", "Error 3"]
        formatted = self.agent._format_validation_errors(errors)

        self.assertIn("Found 3 validation errors", formatted)
        self.assertIn("1. Error 1", formatted)
        self.assertIn("2. Error 2", formatted)
        self.assertIn("3. Error 3", formatted)


if __name__ == "__main__":
    unittest.main()
