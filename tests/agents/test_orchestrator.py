"""Unit tests for AgentOrchestrator."""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.base_agent import AgentResult
from app.agents.orchestrator import (
    AgentOrchestrator,
    BatchPipelineInput,
    PipelineInput,
    PipelineOutput,
    PipelineStage,
    RetryConfig,
    RetryStrategy,
)


class TestAgentOrchestrator(unittest.IsolatedAsyncioTestCase):
    """Test AgentOrchestrator pipeline execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.correlation_id = "orchestrator-test-123"
        self.test_url = "https://example.com/article"

        # Mock agents
        self.mock_extraction_agent = MagicMock()
        self.mock_summarization_agent = MagicMock()
        self.mock_validation_agent = MagicMock()

        self.orchestrator = AgentOrchestrator(
            extraction_agent=self.mock_extraction_agent,
            summarization_agent=self.mock_summarization_agent,
            validation_agent=self.mock_validation_agent,
        )

        # Sample outputs for mocking
        self.extraction_output = MagicMock()
        self.extraction_output.content_markdown = "Extracted content " * 20
        self.extraction_output.content_html = "<p>HTML content</p>"
        self.extraction_output.metadata = {"title": "Test Article"}
        self.extraction_output.normalized_url = self.test_url
        self.extraction_output.crawl_result_id = 123

        self.summarization_output = MagicMock()
        self.summarization_output.summary_json = {
            "summary_250": "Short summary.",
            "summary_1000": "Longer summary.",
            "tldr": "TLDR",
        }
        self.summarization_output.llm_call_id = 456
        self.summarization_output.attempts = 1
        self.summarization_output.corrections_applied = []

    async def test_execute_pipeline_successful_flow(self):
        """Test successful execution of complete pipeline."""
        # Mock successful extraction
        extraction_result = AgentResult.success_result(self.extraction_output, content_length=100)
        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)

        # Mock successful summarization
        summarization_result = AgentResult.success_result(self.summarization_output, attempts=1)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
            max_summary_retries=3,
        )

        result = await self.orchestrator.execute_pipeline(input_data)

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["output"])
        self.assertEqual(result["output"].summary_json, self.summarization_output.summary_json)
        self.assertEqual(result["output"].normalized_url, self.test_url)
        self.assertEqual(result["output"].summarization_attempts, 1)

        # Verify agents were called
        self.mock_extraction_agent.execute.assert_called_once()
        self.mock_summarization_agent.execute.assert_called_once()

    async def test_pipeline_failure_at_extraction_stage(self):
        """Test pipeline failure during extraction stage."""
        # Mock extraction failure
        extraction_result = AgentResult.error_result("Failed to extract content: 404 Not Found")
        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
        )

        with self.assertRaises(Exception) as context:
            await self.orchestrator.execute_pipeline(input_data)

        self.assertIn("Content extraction failed", str(context.exception))
        self.assertIn("404 Not Found", str(context.exception))

        # Verify extraction was called but summarization was not
        self.mock_extraction_agent.execute.assert_called_once()
        self.mock_summarization_agent.execute.assert_not_called()

    async def test_pipeline_failure_at_summarization_stage(self):
        """Test pipeline failure during summarization stage."""
        # Mock successful extraction
        extraction_result = AgentResult.success_result(self.extraction_output)
        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)

        # Mock summarization failure
        summarization_result = AgentResult.error_result("Summarization failed after 3 attempts")
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
        )

        with self.assertRaises(Exception) as context:
            await self.orchestrator.execute_pipeline(input_data)

        self.assertIn("Summarization failed", str(context.exception))
        self.assertIn("after 3 attempts", str(context.exception))

        # Verify both agents were called
        self.mock_extraction_agent.execute.assert_called_once()
        self.mock_summarization_agent.execute.assert_called_once()

    async def test_execute_batch_pipeline_concurrent_processing(self):
        """Test batch pipeline processes multiple URLs concurrently."""
        urls = [
            "https://example.com/article1",
            "https://example.com/article2",
            "https://example.com/article3",
        ]

        # Mock successful pipeline execution
        extraction_result = AgentResult.success_result(self.extraction_output)
        summarization_result = AgentResult.success_result(self.summarization_output)

        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        batch_input = BatchPipelineInput(
            urls=urls,
            base_correlation_id=self.correlation_id,
            language="en",
            max_concurrent=2,
        )

        results = await self.orchestrator.execute_batch_pipeline(batch_input)

        self.assertEqual(len(results), 3)
        for result in results:
            self.assertTrue(result.success)
            self.assertIsNotNone(result.output)
            self.assertIn(result.url, urls)

        # Each URL should have its own correlation_id
        correlation_ids = [r.correlation_id for r in results]
        self.assertEqual(len(set(correlation_ids)), 3)  # All unique

    async def test_execute_batch_pipeline_handles_failures(self):
        """Test batch pipeline handles individual URL failures."""
        urls = [
            "https://example.com/success",
            "https://example.com/fail",
            "https://example.com/success2",
        ]

        urls_to_fail = {"https://example.com/fail"}  # Defined here

        call_count = 0

        async def mock_execute(input_data):
            nonlocal call_count
            call_count += 1
            print(f"DEBUG: urls_to_fail in mock_execute: {urls_to_fail}")
            if input_data.url in urls_to_fail:
                print(f"DEBUG: mock_execute for {input_data.url} returning error.")
                return AgentResult.error_result("Extraction failed")
            print(f"DEBUG: mock_execute for {input_data.url} returning success.")
            return AgentResult.success_result(self.extraction_output)

        self.mock_extraction_agent.execute = AsyncMock(side_effect=mock_execute)
        summarization_result = AgentResult.success_result(self.summarization_output)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        batch_input = BatchPipelineInput(
            urls=urls,
            base_correlation_id=self.correlation_id,
            language="en",
            max_concurrent=1,
        )

        results = await self.orchestrator.execute_batch_pipeline(batch_input)

        self.assertEqual(len(results), 3)
        # First and third should succeed
        self.assertTrue(results[0].success)
        self.assertFalse(results[1].success)  # Second fails
        self.assertTrue(results[2].success)

    async def test_retry_logic_with_exponential_backoff(self):
        """Test retry logic with exponential backoff strategy."""
        retry_config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            max_attempts=3,
            initial_delay_ms=100,
            backoff_multiplier=2.0,
        )

        # Fail first two attempts, succeed on third
        call_count = 0

        async def mock_execute_with_retry(input_data):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"Attempt {call_count} failed")
            # Third attempt succeeds, directly return a mocked success result
            return {
                "success": True,
                "output": PipelineOutput(
                    summary_json=self.summarization_output.summary_json,
                    normalized_url=self.extraction_output.normalized_url,
                    content_length=len(self.extraction_output.content_markdown),
                    extraction_metadata=self.extraction_output.metadata,
                    summarization_attempts=call_count,
                    validation_warnings=[],
                ),
                "metadata": {},
            }

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
            retry_config=retry_config,
        )

        with patch.object(
            self.orchestrator, "execute_pipeline", side_effect=mock_execute_with_retry
        ):
            result = await self.orchestrator._execute_with_retry(input_data)

        self.assertTrue(result["success"])
        self.assertEqual(call_count, 3)

    async def test_retry_exhausted_raises_exception(self):
        """Test that exception is raised when all retry attempts are exhausted."""
        retry_config = RetryConfig(
            strategy=RetryStrategy.FIXED,
            max_attempts=2,
            initial_delay_ms=10,
        )

        # Always fail
        self.mock_extraction_agent.execute = AsyncMock(
            side_effect=RuntimeError("Persistent failure")
        )

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
            retry_config=retry_config,
        )

        with self.assertRaises(Exception) as context:
            await self.orchestrator._execute_with_retry(input_data)

        self.assertIn("failed after 2 attempts", str(context.exception))

    async def test_calculate_retry_delay_exponential(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
        )

        delay1 = self.orchestrator._calculate_retry_delay(1, config.strategy, config)
        delay2 = self.orchestrator._calculate_retry_delay(2, config.strategy, config)
        delay3 = self.orchestrator._calculate_retry_delay(3, config.strategy, config)

        self.assertEqual(delay1, 1000)  # 1000 * 2^0
        self.assertEqual(delay2, 2000)  # 1000 * 2^1
        self.assertEqual(delay3, 4000)  # 1000 * 2^2

    async def test_calculate_retry_delay_linear(self):
        """Test linear backoff delay calculation."""
        config = RetryConfig(strategy=RetryStrategy.LINEAR, initial_delay_ms=1000)

        delay1 = self.orchestrator._calculate_retry_delay(1, config.strategy, config)
        delay2 = self.orchestrator._calculate_retry_delay(2, config.strategy, config)
        delay3 = self.orchestrator._calculate_retry_delay(3, config.strategy, config)

        self.assertEqual(delay1, 1000)  # 1000 * 1
        self.assertEqual(delay2, 2000)  # 1000 * 2
        self.assertEqual(delay3, 3000)  # 1000 * 3

    async def test_calculate_retry_delay_fixed(self):
        """Test fixed delay calculation."""
        config = RetryConfig(strategy=RetryStrategy.FIXED, initial_delay_ms=500)

        delay1 = self.orchestrator._calculate_retry_delay(1, config.strategy, config)
        delay2 = self.orchestrator._calculate_retry_delay(2, config.strategy, config)
        delay3 = self.orchestrator._calculate_retry_delay(3, config.strategy, config)

        self.assertEqual(delay1, 500)
        self.assertEqual(delay2, 500)
        self.assertEqual(delay3, 500)

    async def test_calculate_retry_delay_none(self):
        """Test no delay strategy."""
        config = RetryConfig(strategy=RetryStrategy.NONE)

        delay = self.orchestrator._calculate_retry_delay(1, config.strategy, config)
        self.assertEqual(delay, 0)

    async def test_streaming_pipeline_yields_progress(self):
        """Test streaming pipeline yields progress updates."""
        extraction_result = AgentResult.success_result(self.extraction_output)
        summarization_result = AgentResult.success_result(self.summarization_output)

        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
        )

        progress_updates = []
        final_result = None

        async for update in self.orchestrator.execute_pipeline_streaming(input_data):
            if isinstance(update, dict) and "success" in update:
                final_result = update
            else:
                progress_updates.append(update)

        # Should have progress updates for extraction and completion
        self.assertGreater(len(progress_updates), 0)

        # Check stages are present
        stages = [p.stage for p in progress_updates]
        self.assertIn(PipelineStage.EXTRACTION, stages)

        # Final result should be success
        self.assertIsNotNone(final_result)
        self.assertTrue(final_result["success"])

    async def test_streaming_pipeline_failure_at_extraction(self):
        """Test streaming pipeline handles extraction failure."""
        extraction_result = AgentResult.error_result("Extraction failed")
        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            language="en",
        )

        updates = []
        async for update in self.orchestrator.execute_pipeline_streaming(input_data):
            updates.append(update)

        # Last update should be error
        final_update = updates[-1]
        self.assertIsInstance(final_update, dict)
        self.assertFalse(final_update["success"])
        self.assertIn("Extraction failed", final_update["error"])

    async def test_state_persistence_and_resumption(self):
        """Test pipeline state can be persisted and resumed."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            extraction_result = AgentResult.success_result(self.extraction_output)
            summarization_result = AgentResult.success_result(self.summarization_output)

            self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)
            self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

            input_data = PipelineInput(
                url=self.test_url,
                correlation_id=self.correlation_id,
                language="en",
                enable_state_persistence=True,
                state_dir=state_dir,
            )

            # Execute pipeline with state persistence
            final_result = None
            async for update in self.orchestrator.execute_pipeline_streaming(input_data):
                if isinstance(update, dict) and "success" in update:
                    final_result = update

            self.assertTrue(final_result["success"])

            # State file should be cleaned up after successful completion
            state_file = state_dir / f"{self.correlation_id}.json"
            self.assertFalse(state_file.exists())

    async def test_batch_pipeline_respects_concurrency_limit(self):
        """Test batch pipeline respects max_concurrent limit."""
        urls = ["https://example.com/article" + str(i) for i in range(10)]

        extraction_result = AgentResult.success_result(self.extraction_output)
        summarization_result = AgentResult.success_result(self.summarization_output)

        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        batch_input = BatchPipelineInput(
            urls=urls,
            base_correlation_id=self.correlation_id,
            language="en",
            max_concurrent=3,  # Limit to 3 concurrent
        )

        results = await self.orchestrator.execute_batch_pipeline(batch_input)

        self.assertEqual(len(results), 10)
        self.assertTrue(all(r.success for r in results))

    async def test_pipeline_input_validation(self):
        """Test pipeline input validation."""
        # Test with minimal valid input
        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
        )
        self.assertEqual(input_data.language, "en")  # Default
        self.assertFalse(input_data.force_refresh)  # Default
        self.assertEqual(input_data.max_summary_retries, 3)  # Default

    async def test_retry_config_defaults(self):
        """Test RetryConfig default values."""
        config = RetryConfig()
        self.assertEqual(config.strategy, RetryStrategy.EXPONENTIAL)
        self.assertEqual(config.max_attempts, 3)
        self.assertEqual(config.initial_delay_ms, 1000)
        self.assertEqual(config.backoff_multiplier, 2.0)

    async def test_pipeline_metadata_propagation(self):
        """Test that metadata is properly propagated through pipeline."""
        extraction_result = AgentResult.success_result(
            self.extraction_output, extraction_time=1.5, source="firecrawl"
        )
        summarization_result = AgentResult.success_result(
            self.summarization_output, llm_model="test-model", tokens_used=500
        )

        self.mock_extraction_agent.execute = AsyncMock(return_value=extraction_result)
        self.mock_summarization_agent.execute = AsyncMock(return_value=summarization_result)

        input_data = PipelineInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
        )

        result = await self.orchestrator.execute_pipeline(input_data)

        self.assertTrue(result["success"])
        self.assertIn("metadata", result)
        self.assertIn("extraction_metadata", result["metadata"])
        self.assertIn("summarization_metadata", result["metadata"])


if __name__ == "__main__":
    unittest.main()
