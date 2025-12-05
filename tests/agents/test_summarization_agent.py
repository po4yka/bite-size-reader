"""Unit tests for SummarizationAgent."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.base_agent import AgentResult
from app.agents.summarization_agent import SummarizationAgent, SummarizationInput


class TestSummarizationAgent(unittest.IsolatedAsyncioTestCase):
    """Test SummarizationAgent functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.correlation_id = "summarization-test-123"
        self.mock_llm_summarizer = MagicMock()
        self.mock_validator = MagicMock()

        self.agent = SummarizationAgent(
            llm_summarizer=self.mock_llm_summarizer,
            validator_agent=self.mock_validator,
            correlation_id=self.correlation_id,
        )

        self.valid_summary = {
            "summary_250": "Short summary.",
            "summary_1000": "Longer summary with more details.",
            "tldr": "TLDR",
            "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
            "topic_tags": ["#tech", "#ai"],
            "entities": {
                "people": ["John Doe"],
                "organizations": ["OpenAI"],
                "locations": ["SF"],
            },
            "estimated_reading_time_min": 5,
            "key_stats": [],
            "answered_questions": [],
            "readability": {"score": 12.0, "level": "College"},
            "seo_keywords": ["ai", "tech"],
        }

        self.content = "This is test content to summarize. " * 10

    async def test_successful_summarization_first_attempt(self):
        """Test successful summarization on the first attempt."""
        # Mock LLM to return valid summary
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(return_value=self.valid_summary)

        # Mock validator to pass
        validation_result = AgentResult.success_result({"summary_json": self.valid_summary})
        self.mock_validator.execute = AsyncMock(return_value=validation_result)

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=3,
        )

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.output)
        self.assertEqual(result.output.summary_json, self.valid_summary)
        self.assertEqual(result.output.attempts, 1)
        self.assertEqual(len(result.output.corrections_applied), 0)

        # Verify LLM was called once
        self.mock_llm_summarizer.summarize_content_pure.assert_called_once()

        # Verify validator was called once
        self.mock_validator.execute.assert_called_once()

    async def test_self_correction_on_validation_failure(self):
        """Test self-correction loop when validation fails initially."""
        # First attempt: invalid summary
        invalid_summary = self.valid_summary.copy()
        invalid_summary["summary_250"] = "X" * 300  # Too long

        # Second attempt: valid summary
        valid_summary = self.valid_summary.copy()

        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(
            side_effect=[invalid_summary, valid_summary]
        )

        # First validation fails, second passes
        validation_error = AgentResult.error_result(
            "summary_250 exceeds limit: 300 chars (max 250)"
        )
        validation_success = AgentResult.success_result({"summary_json": valid_summary})
        self.mock_validator.execute = AsyncMock(side_effect=[validation_error, validation_success])

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=3,
        )

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertEqual(result.output.attempts, 2)
        self.assertEqual(len(result.output.corrections_applied), 1)
        self.assertIn("summary_250 exceeds limit", result.output.corrections_applied[0])

        # Verify LLM was called twice
        self.assertEqual(self.mock_llm_summarizer.summarize_content_pure.call_count, 2)

        # Verify second call included feedback
        second_call_args = self.mock_llm_summarizer.summarize_content_pure.call_args_list[1]
        self.assertIsNotNone(second_call_args[1].get("feedback_instructions"))

    async def test_max_retry_limit_respected(self):
        """Test that max retry limit is respected when validation keeps failing."""
        # Always return invalid summary
        invalid_summary = {"summary_250": "X" * 300}
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(return_value=invalid_summary)

        # Validation always fails
        validation_error = AgentResult.error_result("summary_250 exceeds limit: 300 chars")
        self.mock_validator.execute = AsyncMock(return_value=validation_error)

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=3,
        )

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("LLM repeatedly returned identical response", result.error)
        self.assertEqual(result.metadata["attempts"], 3)
        self.assertEqual(len(result.metadata["corrections_attempted"]), 4)

        # Verify LLM was called max_retries times
        self.assertEqual(self.mock_llm_summarizer.summarize_content_pure.call_count, 3)

    async def test_error_feedback_included_in_retry_prompts(self):
        """Test that error feedback is included in retry prompts."""
        # First: validation error, Second: success
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(
            side_effect=[{"summary_250": "X" * 300}, self.valid_summary]
        )

        validation_error = AgentResult.error_result(
            "summary_250 exceeds limit: 300 chars (max 250). "
            "Truncate to last sentence boundary before 250 chars."
        )
        validation_success = AgentResult.success_result({"summary_json": self.valid_summary})
        self.mock_validator.execute = AsyncMock(side_effect=[validation_error, validation_success])

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=3,
        )

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)

        # Verify second call to LLM included feedback_instructions
        second_call = self.mock_llm_summarizer.summarize_content_pure.call_args_list[1]
        feedback = second_call[1].get("feedback_instructions")
        self.assertIsNotNone(feedback)
        self.assertIn("CORRECTIONS NEEDED", feedback)
        self.assertIn("summary_250 exceeds limit", feedback)
        self.assertIn("Truncate to last sentence", feedback)

    async def test_llm_returns_none_handled(self):
        """Test that None return from LLM is handled gracefully."""
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(return_value=None)

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=2,
        )

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("LLM returned no result", result.error)

    async def test_llm_raises_value_error_handled(self):
        """Test that ValueError from LLM is handled."""
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(
            side_effect=ValueError("Summarization failed")
        )

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=2,
        )

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("failed after 2 attempts", result.error)

    async def test_llm_raises_unexpected_exception_handled(self):
        """Test that unexpected exceptions from LLM are handled."""
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=2,
        )

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("Exception", result.metadata["corrections_attempted"][0])

    async def test_duplicate_response_detection(self):
        """Test detection of duplicate LLM responses (feedback ignored)."""
        # Return same summary multiple times (LLM ignoring feedback)
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(
            return_value={"summary_250": "X" * 300}
        )

        validation_error = AgentResult.error_result("summary_250 exceeds limit")
        self.mock_validator.execute = AsyncMock(return_value=validation_error)

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=5,  # Set high to test early abort
        )

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("identical response", result.error.lower())
        self.assertTrue(result.metadata.get("feedback_ignored", False))

        # Should abort before max_retries due to duplicate detection
        self.assertLessEqual(self.mock_llm_summarizer.summarize_content_pure.call_count, 5)

    async def test_system_prompt_loaded_for_language(self):
        """Test that correct system prompt is loaded for language."""
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(return_value=self.valid_summary)
        validation_success = AgentResult.success_result({"summary_json": self.valid_summary})
        self.mock_validator.execute = AsyncMock(return_value=validation_success)

        # Test English
        input_data_en = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=1,
        )

        with patch.object(self.agent, "_get_system_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = "English system prompt"
            await self.agent.execute(input_data_en)
            mock_get_prompt.assert_called_with("en")

        # Test Russian
        input_data_ru = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="ru",
            max_retries=1,
        )

        with patch.object(self.agent, "_get_system_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = "Russian system prompt"
            await self.agent.execute(input_data_ru)
            mock_get_prompt.assert_called_with("ru")

    async def test_build_correction_prompt_groups_errors(self):
        """Test that correction prompt groups errors by type."""
        errors = [
            "summary_250 exceeds limit: 300 chars (max 250)",
            "Topic tags missing '#' prefix: invalid",
            "Missing required fields: key_ideas",
            "Invalid JSON structure",
        ]

        prompt = self.agent._build_correction_prompt(errors)

        self.assertIn("CORRECTIONS NEEDED", prompt)
        self.assertIn("Character Limits", prompt)
        self.assertIn("Topic Tags", prompt)
        self.assertIn("Required Fields", prompt)
        self.assertIn("JSON Structure", prompt)

    async def test_build_correction_prompt_empty_errors(self):
        """Test that empty errors list returns empty prompt."""
        prompt = self.agent._build_correction_prompt([])
        self.assertEqual(prompt, "")

    async def test_calculate_response_hash_consistent(self):
        """Test that response hash is consistent for same content."""
        response1 = {"summary_250": "Test", "key_ideas": ["a", "b"]}
        response2 = {"key_ideas": ["a", "b"], "summary_250": "Test"}  # Different order

        hash1 = self.agent._calculate_response_hash(response1)
        hash2 = self.agent._calculate_response_hash(response2)

        # Should be same due to sort_keys=True
        self.assertEqual(hash1, hash2)

    async def test_calculate_response_hash_different_content(self):
        """Test that different content produces different hashes."""
        response1 = {"summary_250": "Test A"}
        response2 = {"summary_250": "Test B"}

        hash1 = self.agent._calculate_response_hash(response1)
        hash2 = self.agent._calculate_response_hash(response2)

        self.assertNotEqual(hash1, hash2)

    async def test_multiple_corrections_tracked(self):
        """Test that multiple correction attempts are all tracked."""
        # Three attempts: two failures, one success
        summaries = [
            {"summary_250": "X" * 300},  # Too long
            {"summary_250": "Short", "topic_tags": ["invalid"]},  # No # prefix
            self.valid_summary,  # Valid
        ]
        self.mock_llm_summarizer.summarize_content_pure = AsyncMock(side_effect=summaries)

        validation_results = [
            AgentResult.error_result("summary_250 exceeds limit"),
            AgentResult.error_result("Topic tags missing '#' prefix"),
            AgentResult.success_result({"summary_json": self.valid_summary}),
        ]
        self.mock_validator.execute = AsyncMock(side_effect=validation_results)

        input_data = SummarizationInput(
            content=self.content,
            correlation_id=self.correlation_id,
            language="en",
            max_retries=3,
        )

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertEqual(result.output.attempts, 3)
        self.assertEqual(len(result.output.corrections_applied), 2)
        self.assertIn("summary_250 exceeds limit", result.output.corrections_applied[0])
        self.assertIn("Topic tags missing", result.output.corrections_applied[1])


if __name__ == "__main__":
    unittest.main()
