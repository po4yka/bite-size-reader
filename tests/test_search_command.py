"""Tests for the /search command functionality."""

import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database
from app.services.topic_search import TopicArticle


class FakeMessage:
    """Mock Telegram message for testing."""

    def __init__(self, text: str, uid: int = 1):
        class _User:
            def __init__(self, id):
                self.id = id

        class _Chat:
            id = 1

        self.text = text
        self.chat = _Chat()
        self.from_user = _User(uid)
        self._replies: list[str] = []
        self.id = 123
        self.message_id = 123

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        _ = parse_mode
        self._replies.append(text)


class BotSpy(TelegramBot):
    """Test spy for TelegramBot that tracks behavior."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.seen_urls: list[str] = []

    async def _handle_url_flow(self, message: Any, url_text: str, **_: object) -> None:
        self.seen_urls.append(url_text)
        await self._safe_reply(message, f"OK {url_text}")


def make_bot(tmp_path: str) -> BotSpy:
    """Create test bot instance with mocked dependencies."""
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1, 42)),
        firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
        openrouter=OpenRouterConfig(
            api_key="y",
            model="m",
            fallback_models=(),
            http_referer=None,
            x_title=None,
            max_tokens=None,
            top_p=None,
            temperature=0.2,
        ),
        runtime=RuntimeConfig(
            db_path=tmp_path,
            log_level="INFO",
            request_timeout_sec=5,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    # Mock the OpenRouter client to avoid API key validation
    with patch("app.adapters.telegram.telegram_bot.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return BotSpy(cfg=cfg, db=db)


class TestSearchCommand(unittest.IsolatedAsyncioTestCase):
    """Test cases for the /search command."""

    async def test_search_command_with_results(self):
        """Test /search command returns results successfully."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search service
            class FakeHybridSearch:
                def __init__(self) -> None:
                    self.queries: list[tuple[str, str | None]] = []

                async def search(
                    self,
                    query: str,
                    *,
                    filters=None,
                    correlation_id: str | None = None,
                ) -> list[TopicArticle]:
                    self.queries.append((query, correlation_id))
                    return [
                        TopicArticle(
                            title="Machine Learning Fundamentals",
                            url="https://example.com/ml-fundamentals",
                            snippet="An introduction to machine learning concepts and algorithms.",
                            source="ML Weekly",
                            published_at="2024-01-15",
                        ),
                        TopicArticle(
                            title="Deep Learning with Python",
                            url="https://example.com/deep-learning-python",
                            snippet="Practical guide to building neural networks with Python.",
                            source="Tech Blog",
                            published_at="2024-02-20",
                        ),
                        TopicArticle(
                            title="AI Ethics and Safety",
                            url="https://example.com/ai-ethics",
                            snippet="Exploring ethical considerations in artificial intelligence.",
                            source="AI Journal",
                            published_at="2024-03-10",
                        ),
                    ]

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search machine learning")
            await bot._on_message(msg)

            # Verify search was called with correct query
            assert fake_search.queries
            assert fake_search.queries[0][0] == "machine learning"

            # Verify response contains results
            replies = " ".join(msg._replies)
            assert "Search Results" in replies
            assert "machine learning" in replies
            assert "Found 3 article(s)" in replies
            assert "Machine Learning Fundamentals" in replies
            assert "Deep Learning with Python" in replies
            assert "AI Ethics and Safety" in replies
            assert "https://example.com/ml-fundamentals" in replies

    async def test_search_command_no_results(self):
        """Test /search command when no results are found."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search returning empty results
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    return []

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search nonexistent topic xyz")
            await bot._on_message(msg)

            # Verify empty results message
            replies = " ".join(msg._replies)
            assert "No articles found" in replies
            assert "nonexistent topic xyz" in replies
            assert "Broader search terms" in replies
            assert "/find" in replies

    async def test_search_command_without_query(self):
        """Test /search command without providing a query shows usage."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search (should not be called)
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    msg = "Should not be called when query is missing"
                    raise AssertionError(msg)

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search")
            await bot._on_message(msg)

            # Verify usage message
            replies = " ".join(msg._replies)
            assert "Usage:" in replies
            assert "/search <query>" in replies
            assert "Examples:" in replies
            assert "machine learning" in replies
            assert "Semantic vector search" in replies
            assert "Keyword (FTS) search" in replies

    async def test_search_command_service_unavailable(self):
        """Test /search command when hybrid search service is not available."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Set hybrid search to None (unavailable)
            bot.hybrid_search_service = None
            bot.message_handler.command_processor.hybrid_search = None

            msg = FakeMessage("/search test query")
            await bot._on_message(msg)

            # Verify unavailable message
            replies = " ".join(msg._replies)
            assert "Semantic search is currently unavailable" in replies

    async def test_search_command_with_error(self):
        """Test /search command handles errors gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search that raises an error
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    raise RuntimeError("Simulated search error")

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search error test")
            await bot._on_message(msg)

            # Verify error handling
            replies = " ".join(msg._replies)
            assert "Search failed" in replies
            assert "try again" in replies.lower()

    async def test_search_command_truncates_long_titles(self):
        """Test /search command truncates long titles and snippets."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search with very long title and snippet
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    return [
                        TopicArticle(
                            title="A" * 150,  # Very long title
                            url="https://example.com/long",
                            snippet="B" * 200,  # Very long snippet
                            source="Example",
                            published_at="2024-01-01",
                        )
                    ]

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search test")
            await bot._on_message(msg)

            # Verify truncation happened
            replies = " ".join(msg._replies)
            assert "..." in replies
            # Title should be truncated to 100 chars (97 + "...")
            assert "A" * 97 in replies
            # Snippet should be truncated to 150 chars (147 + "...")
            assert "B" * 147 in replies

    async def test_search_command_displays_metadata(self):
        """Test /search command displays source and published date."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search with metadata
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    return [
                        TopicArticle(
                            title="Article with Metadata",
                            url="https://example.com/article",
                            snippet="Test article",
                            source="Tech News Daily",
                            published_at="2024-06-15",
                        ),
                        TopicArticle(
                            title="Article without Metadata",
                            url="https://example.com/article2",
                            snippet="Another test",
                            source=None,
                            published_at=None,
                        ),
                    ]

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search metadata test")
            await bot._on_message(msg)

            # Verify metadata display
            replies = " ".join(msg._replies)
            assert "Tech News Daily" in replies
            assert "2024-06-15" in replies
            assert "📰" in replies  # Source emoji
            assert "📅" in replies  # Date emoji

    async def test_search_command_limits_to_ten_results(self):
        """Test /search command limits results to top 10."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search returning 15 results
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    return [
                        TopicArticle(
                            title=f"Article {i}",
                            url=f"https://example.com/article{i}",
                            snippet=f"Snippet {i}",
                            source=None,
                            published_at=None,
                        )
                        for i in range(1, 16)
                    ]

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search many results")
            await bot._on_message(msg)

            # Verify only 10 results shown
            replies = " ".join(msg._replies)
            assert "Found 15 article(s)" in replies
            assert "Article 1" in replies
            assert "Article 10" in replies
            # Articles 11-15 should not be displayed
            assert "Article 11" not in replies
            assert "Article 15" not in replies

    async def test_search_command_interaction_tracking(self):
        """Test /search command tracks user interactions in database."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Mock hybrid search
            class FakeHybridSearch:
                async def search(
                    self, query: str, *, filters=None, correlation_id: str | None = None
                ):
                    return [
                        TopicArticle(
                            title="Test Article",
                            url="https://example.com/test",
                            snippet="Test snippet",
                            source=None,
                            published_at=None,
                        )
                    ]

            fake_search = FakeHybridSearch()
            bot.hybrid_search_service = fake_search
            bot.message_handler.command_processor.hybrid_search = fake_search

            msg = FakeMessage("/search interaction test", uid=42)
            await bot._on_message(msg)

            # Verify interaction was tracked in database
            interactions = bot.db.get_user_interactions(uid=42, limit=10)
            assert len(interactions) > 0
            last_interaction = interactions[0]
            assert last_interaction["command"] == "search"
            assert last_interaction["response_type"] == "search_results"
            assert last_interaction["response_sent"] is True


class TestSearchServiceIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for search service initialization."""

    async def test_search_services_initialized_on_bot_creation(self):
        """Test that all search services are properly initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))

            # Verify all services are initialized
            assert bot.embedding_service is not None
            assert bot.vector_search_service is not None
            assert bot.query_expansion_service is not None
            assert bot.hybrid_search_service is not None

            # Verify services are wired correctly
            assert bot.message_handler.command_processor.hybrid_search is not None
            assert (
                bot.message_handler.command_processor.hybrid_search
                == bot.hybrid_search_service
            )

    async def test_search_service_parameters(self):
        """Test that search services are configured with correct parameters."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))

            # Check query expansion settings
            assert bot.query_expansion_service._max_expansions == 5
            assert bot.query_expansion_service._use_synonyms is True

            # Check vector search settings
            assert bot.vector_search_service._min_similarity == 0.3

            # Check hybrid search weights
            assert bot.hybrid_search_service._fts_weight == 0.4
            assert bot.hybrid_search_service._vector_weight == 0.6


if __name__ == "__main__":
    unittest.main()
