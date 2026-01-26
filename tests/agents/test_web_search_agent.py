"""Unit tests for WebSearchAgent and SearchContextBuilder."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.adapters.content.search_context_builder import SearchContextBuilder
from app.agents.web_search_agent import (
    SearchAnalysisResult,
    WebSearchAgent,
    WebSearchAgentInput,
    WebSearchAgentOutput,
)


class MockTopicArticle:
    """Mock TopicArticle for testing."""

    def __init__(
        self,
        title: str = "Test Article",
        url: str = "https://example.com/article",
        snippet: str | None = "This is a test snippet.",
        source: str | None = "Example News",
        published_at: str | None = "2024-01-15",
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source
        self.published_at = published_at


class MockWebSearchConfig:
    """Mock WebSearchConfig for testing."""

    def __init__(
        self,
        enabled: bool = True,
        max_queries: int = 3,
        min_content_length: int = 500,
        timeout_sec: float = 10.0,
        max_context_chars: int = 2000,
        cache_ttl_sec: int = 3600,
    ):
        self.enabled = enabled
        self.max_queries = max_queries
        self.min_content_length = min_content_length
        self.timeout_sec = timeout_sec
        self.max_context_chars = max_context_chars
        self.cache_ttl_sec = cache_ttl_sec


class MockLLMResult:
    """Mock LLM result for testing."""

    def __init__(self, status: str = "ok", response_text: str = "", error_text: str | None = None):
        self.status = status
        self.response_text = response_text
        self.error_text = error_text


class TestSearchContextBuilder(unittest.TestCase):
    """Tests for SearchContextBuilder."""

    def setUp(self):
        """Set up test fixtures."""
        self.builder = SearchContextBuilder(max_chars=2000)

    def test_empty_articles_returns_empty_string(self):
        """Test that empty article list returns empty string."""
        result = self.builder.build_context([])
        self.assertEqual(result, "")

    def test_single_article_formatting(self):
        """Test formatting of a single article."""
        article = MockTopicArticle(
            title="Test Title",
            url="https://example.com",
            snippet="Test snippet content.",
            source="Test Source",
            published_at="2024-01-15",
        )
        result = self.builder.build_context([article])

        self.assertIn("**Test Title**", result)
        self.assertIn("Test Source", result)
        self.assertIn("2024-01-15", result)
        self.assertIn("Test snippet content.", result)

    def test_deduplication_by_url(self):
        """Test that duplicate URLs are removed."""
        articles = [
            MockTopicArticle(title="Article 1", url="https://example.com/same"),
            MockTopicArticle(title="Article 2", url="https://example.com/same"),
            MockTopicArticle(title="Article 3", url="https://example.com/different"),
        ]
        result = self.builder.build_context(articles)

        # Should only have 2 unique articles
        self.assertEqual(result.count("**Article"), 2)
        self.assertIn("Article 1", result)
        self.assertIn("Article 3", result)
        self.assertNotIn("Article 2", result)

    def test_character_limit_truncation(self):
        """Test that output respects character limit."""
        builder = SearchContextBuilder(max_chars=300)
        articles = [
            MockTopicArticle(
                title="Long Article Title " * 5,
                snippet="Very long snippet content. " * 20,
            )
            for _ in range(5)
        ]
        result = builder.build_context(articles)

        # Should be under the limit
        self.assertLessEqual(len(result), 350)  # Allow some buffer for formatting

    def test_missing_optional_fields(self):
        """Test handling of articles with missing optional fields."""
        article = MockTopicArticle(
            title="Title Only",
            url="https://example.com",
            snippet=None,
            source=None,
            published_at=None,
        )
        result = self.builder.build_context([article])

        self.assertIn("**Title Only**", result)
        self.assertNotIn("None", result)

    def test_max_chars_validation(self):
        """Test that max_chars must be at least 100."""
        with self.assertRaises(ValueError) as ctx:
            SearchContextBuilder(max_chars=50)
        self.assertIn("at least 100", str(ctx.exception))

    def test_build_context_with_header(self):
        """Test building context with custom header."""
        article = MockTopicArticle()
        result = self.builder.build_context_with_header([article], header="CUSTOM HEADER:")

        self.assertIn("CUSTOM HEADER:", result)
        self.assertIn("Test Article", result)

    def test_build_context_with_default_header(self):
        """Test building context with default header."""
        article = MockTopicArticle()
        result = self.builder.build_context_with_header([article])

        self.assertIn("ADDITIONAL WEB CONTEXT", result)
        self.assertIn("retrieved", result)


class TestWebSearchAgent(unittest.IsolatedAsyncioTestCase):
    """Tests for WebSearchAgent."""

    def setUp(self):
        """Set up test fixtures."""
        self.correlation_id = "web-search-test-123"
        self.mock_llm = MagicMock()
        self.mock_llm.chat = AsyncMock()
        self.mock_search = MagicMock()
        self.mock_search.find_articles = AsyncMock()
        self.config = MockWebSearchConfig()

    def _create_agent(self):
        """Create agent with mocks."""
        return WebSearchAgent(
            llm_client=self.mock_llm,
            search_service=self.mock_search,
            cfg=self.config,
            correlation_id=self.correlation_id,
        )

    async def test_short_content_skips_search(self):
        """Test that content shorter than min_content_length skips search."""
        self.config.min_content_length = 500
        agent = self._create_agent()

        input_data = WebSearchAgentInput(
            content="Short content" * 10,  # ~130 chars
            language="en",
        )
        result = await agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertFalse(result.output.searched)
        self.assertIn("too short", result.output.reason)
        self.mock_llm.chat.assert_not_called()
        self.mock_search.find_articles.assert_not_called()

    async def test_search_not_needed_returns_empty(self):
        """Test when LLM determines search is not needed."""
        agent = self._create_agent()

        # Mock LLM response saying search not needed
        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok",
            response_text='{"needs_search": false, "queries": [], "reason": "Content is self-contained"}',
        )

        input_data = WebSearchAgentInput(
            content="A" * 1000,  # Long enough content
            language="en",
        )
        result = await agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertFalse(result.output.searched)
        self.assertEqual(result.output.context, "")
        self.assertEqual(result.output.reason, "Content is self-contained")

    async def test_search_executed_when_needed(self):
        """Test that search is executed when LLM recommends it."""
        agent = self._create_agent()

        # Mock LLM response recommending search
        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok",
            response_text='{"needs_search": true, "queries": ["ACME Corp acquisition 2024"], "reason": "Need context on recent merger"}',
        )

        # Mock search results
        self.mock_search.find_articles.return_value = [
            MockTopicArticle(title="ACME Acquires GlobalTech", snippet="Details about the merger.")
        ]

        input_data = WebSearchAgentInput(
            content="A" * 1000,
            language="en",
        )
        result = await agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertTrue(result.output.searched)
        self.assertEqual(result.output.queries_executed, ["ACME Corp acquisition 2024"])
        self.assertEqual(result.output.articles_found, 1)
        self.assertIn("ACME Acquires GlobalTech", result.output.context)

    async def test_max_queries_limit_enforced(self):
        """Test that max_queries limit is enforced."""
        self.config.max_queries = 2
        agent = self._create_agent()

        # Mock LLM response with more queries than allowed
        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok",
            response_text='{"needs_search": true, "queries": ["query1", "query2", "query3", "query4"], "reason": "Multiple topics"}',
        )

        self.mock_search.find_articles.return_value = []

        input_data = WebSearchAgentInput(content="A" * 1000, language="en")
        result = await agent.execute(input_data)

        # Should only execute max_queries (2) searches
        self.assertEqual(self.mock_search.find_articles.call_count, 2)
        self.assertEqual(len(result.output.queries_executed), 2)

    async def test_llm_error_returns_graceful_failure(self):
        """Test that LLM errors are handled gracefully."""
        agent = self._create_agent()

        # Mock LLM error
        self.mock_llm.chat.return_value = MockLLMResult(
            status="error", response_text="", error_text="Rate limit exceeded"
        )

        input_data = WebSearchAgentInput(content="A" * 1000, language="en")
        result = await agent.execute(input_data)

        self.assertTrue(result.success)  # Should still succeed (just no search)
        self.assertFalse(result.output.searched)
        self.assertIn("Analysis failed", result.output.reason)

    async def test_search_service_error_handled(self):
        """Test that search service errors are handled gracefully."""
        agent = self._create_agent()

        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok",
            response_text='{"needs_search": true, "queries": ["test query"], "reason": "Need info"}',
        )

        # Mock search service failure
        self.mock_search.find_articles.side_effect = RuntimeError("Search API unavailable")

        input_data = WebSearchAgentInput(content="A" * 1000, language="en")
        result = await agent.execute(input_data)

        # Should still return success but with empty context
        self.assertTrue(result.success)
        self.assertTrue(result.output.searched)
        self.assertEqual(result.output.context, "")  # Empty due to failed search

    async def test_invalid_llm_response_handled(self):
        """Test that invalid LLM responses are handled gracefully."""
        agent = self._create_agent()

        # Mock LLM returning invalid JSON
        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok", response_text="This is not JSON at all"
        )

        input_data = WebSearchAgentInput(content="A" * 1000, language="en")
        result = await agent.execute(input_data)

        self.assertTrue(result.success)
        self.assertFalse(result.output.searched)
        self.assertIn("parse", result.output.reason.lower())

    async def test_language_prompt_selection(self):
        """Test that correct language prompt is selected."""
        agent = self._create_agent()

        self.mock_llm.chat.return_value = MockLLMResult(
            status="ok",
            response_text='{"needs_search": false, "queries": [], "reason": "Self-contained"}',
        )

        # Test with Russian
        input_data = WebSearchAgentInput(content="A" * 1000, language="ru")
        await agent.execute(input_data)

        # Verify LLM was called (we can't easily check prompt content in unit test)
        self.mock_llm.chat.assert_called_once()


class TestSearchAnalysisResult(unittest.TestCase):
    """Tests for SearchAnalysisResult model."""

    def test_model_creation(self):
        """Test creating SearchAnalysisResult."""
        result = SearchAnalysisResult(
            needs_search=True,
            queries=["query1", "query2"],
            reason="Need more context",
        )
        self.assertTrue(result.needs_search)
        self.assertEqual(len(result.queries), 2)
        self.assertEqual(result.reason, "Need more context")

    def test_model_immutability(self):
        """Test that model is immutable (frozen)."""
        from pydantic import ValidationError

        result = SearchAnalysisResult(needs_search=True, queries=["q1"], reason="test")
        with self.assertRaises(ValidationError):
            result.needs_search = False


class TestWebSearchAgentInput(unittest.TestCase):
    """Tests for WebSearchAgentInput model."""

    def test_default_language(self):
        """Test that default language is English."""
        input_data = WebSearchAgentInput(content="test content")
        self.assertEqual(input_data.language, "en")

    def test_custom_language(self):
        """Test setting custom language."""
        input_data = WebSearchAgentInput(content="test", language="ru")
        self.assertEqual(input_data.language, "ru")


class TestWebSearchAgentOutput(unittest.TestCase):
    """Tests for WebSearchAgentOutput model."""

    def test_output_creation(self):
        """Test creating WebSearchAgentOutput."""
        output = WebSearchAgentOutput(
            searched=True,
            context="Search results context",
            queries_executed=["query1", "query2"],
            articles_found=5,
            reason="Found relevant context",
        )
        self.assertTrue(output.searched)
        self.assertEqual(output.articles_found, 5)
        self.assertEqual(len(output.queries_executed), 2)


if __name__ == "__main__":
    unittest.main()
