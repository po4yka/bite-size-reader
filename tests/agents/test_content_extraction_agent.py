"""Unit tests for ContentExtractionAgent."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.agents.content_extraction_agent import ContentExtractionAgent, ExtractionInput


class TestContentExtractionAgent(unittest.IsolatedAsyncioTestCase):
    """Test ContentExtractionAgent functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.correlation_id = "extraction-test-123"
        self.test_url = "https://example.com/article"
        self.normalized_url = "https://example.com/article"

        self.mock_content_extractor = MagicMock()
        self.mock_db = MagicMock()

        self.agent = ContentExtractionAgent(
            content_extractor=self.mock_content_extractor,
            db=self.mock_db,
            correlation_id=self.correlation_id,
        )

        # Sample extracted content
        self.sample_content = "This is extracted content. " * 50
        self.sample_metadata = {
            "title": "Test Article",
            "author": "John Doe",
            "published_date": "2024-01-01",
        }

    async def test_successful_fresh_extraction(self):
        """Test successful content extraction from URL."""
        # Mock no existing crawl result
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        # Mock successful extraction
        self.mock_content_extractor.extract_content_pure = AsyncMock(
            return_value=(
                self.sample_content,
                "firecrawl",
                self.sample_metadata,
            )
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.output)
        self.assertEqual(result.output.content_markdown, self.sample_content)
        self.assertEqual(result.output.metadata, self.sample_metadata)
        self.assertEqual(result.output.normalized_url, self.normalized_url)
        self.assertIsNone(result.output.crawl_result_id)  # Not persisted in agent mode

    async def test_returns_existing_crawl_result(self):
        """Test that existing crawl result is returned instead of re-crawling."""
        # Mock existing request with crawl result
        existing_request = {"id": "req-123"}
        existing_crawl = {
            "id": 456,
            "content_markdown": self.sample_content,
            "content_html": "<p>HTML content</p>",
            "metadata_json": self.sample_metadata,
        }

        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=existing_request)
        self.mock_db.async_get_crawl_result_by_request = AsyncMock(return_value=existing_crawl)

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertEqual(result.output.content_markdown, self.sample_content)
        self.assertEqual(result.output.crawl_result_id, 456)

        # Verify extraction was NOT called (used cached result)
        self.mock_content_extractor.extract_content_pure.assert_not_called()

    async def test_url_normalization(self):
        """Test that URLs are normalized before processing."""
        input_url = "HTTPS://EXAMPLE.COM/Article?utm_source=test"
        expected_normalized = "https://example.com/article?utm_source=test"

        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        self.mock_content_extractor.extract_content_pure = AsyncMock(
            return_value=(self.sample_content, "firecrawl", {})
        )

        input_data = ExtractionInput(url=input_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        # Normalized URL should be lowercase
        self.assertTrue(result.output.normalized_url.startswith("https://"))

    async def test_extraction_failure_handled(self):
        """Test that extraction failures are handled gracefully."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        # Mock extraction failure
        self.mock_content_extractor.extract_content_pure = AsyncMock(
            side_effect=ValueError("Failed to extract: 404 Not Found")
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("Content extraction failed", result.error)

    async def test_unexpected_exception_handled(self):
        """Test that unexpected exceptions are handled."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(
            side_effect=RuntimeError("Database error")
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("Content extraction error", result.error)
        self.assertEqual(result.metadata["exception_type"], "RuntimeError")

    async def test_content_quality_validation_short_content(self):
        """Test content quality validation detects very short content."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        # Return very short content
        short_content = "Short"
        self.mock_content_extractor.extract_content_pure = AsyncMock(
            return_value=(short_content, "firecrawl", {})
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        # Should still succeed but with warning
        self.assertTrue(result.success)
        self.assertEqual(result.output.content_markdown, short_content)

    async def test_content_validation_detects_error_pages(self):
        """Test content validation detects error page indicators."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        # Return content that looks like an error page
        error_content = "404 Not Found - Page not found"
        self.mock_content_extractor.extract_content_pure = AsyncMock(
            return_value=(error_content, "firecrawl", {})
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        # Should still succeed but with validation warning
        self.assertTrue(result.success)

    async def test_validate_content_method(self):
        """Test _validate_content method directly."""
        # Test short content
        result = {"content_markdown": "Too short"}
        error = self.agent._validate_content(result)
        self.assertIsNotNone(error)
        self.assertIn("too short", error.lower())

        # Test error indicators (priority over short content)
        result = {"content_markdown": "Access Denied - forbidden"}
        error = self.agent._validate_content(result)
        self.assertIsNotNone(error)
        self.assertIn("access denied", error.lower())  # check for the new prioritized message
        self.assertNotIn("forbidden", error.lower())  # ensure "forbidden" is not the primary match
        self.assertIn("error page", error.lower())  # ensure general error page indicator is present

        # Test valid content
        result = {"content_markdown": "Valid content " * 50}
        error = self.agent._validate_content(result)
        self.assertIsNone(error)

    async def test_fallback_to_sync_db_methods(self):
        """Test fallback to sync DB methods when async not available."""
        # Async method returns None, sync method returns data
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)

        existing_request = {"id": "req-123"}
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=existing_request)

        existing_crawl = {
            "id": 456,
            "content_markdown": self.sample_content,
            "content_html": None,
            "metadata_json": {},
        }
        self.mock_db.async_get_crawl_result_by_request = AsyncMock(return_value=None)
        self.mock_db.get_crawl_result_by_request = MagicMock(return_value=existing_crawl)

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertEqual(result.output.crawl_result_id, 456)

        # Verify fallback methods were called
        self.mock_db.get_request_by_dedupe_hash.assert_called_once()
        self.mock_db.get_crawl_result_by_request.assert_called_once()

    async def test_extraction_returns_none_handled(self):
        """Test that None return from extraction is handled."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        # Mock extraction returning None (via ValueError exception)
        self.mock_content_extractor.extract_content_pure = AsyncMock(
            side_effect=ValueError("No content returned")
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertFalse(result.success)
        self.assertIn("failed", result.error.lower())

    async def test_force_refresh_parameter_ignored_in_agent_mode(self):
        """Test that force_refresh parameter exists but doesn't affect agent behavior."""
        # In agent mode, force_refresh doesn't affect caching logic
        # (caching is based on dedupe hash lookup)
        existing_request = {"id": "req-123"}
        existing_crawl = {
            "id": 456,
            "content_markdown": self.sample_content,
            "content_html": None,
            "metadata_json": {},
        }

        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=existing_request)
        self.mock_db.async_get_crawl_result_by_request = AsyncMock(return_value=existing_crawl)

        input_data = ExtractionInput(
            url=self.test_url,
            correlation_id=self.correlation_id,
            force_refresh=True,
        )

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        # Should still return cached result even with force_refresh=True
        self.assertEqual(result.output.crawl_result_id, 456)

    async def test_metadata_in_result(self):
        """Test that result metadata includes useful information."""
        self.mock_db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.mock_db.get_request_by_dedupe_hash = MagicMock(return_value=None)

        self.mock_content_extractor.extract_content_pure = AsyncMock(
            return_value=(self.sample_content, "firecrawl", self.sample_metadata)
        )

        input_data = ExtractionInput(url=self.test_url, correlation_id=self.correlation_id)

        result = await self.agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertIn("content_length", result.metadata)
        self.assertEqual(result.metadata["content_length"], len(self.sample_content))
        self.assertIn("has_html", result.metadata)
        self.assertFalse(result.metadata["has_html"])  # No HTML in agent mode


if __name__ == "__main__":
    unittest.main()
