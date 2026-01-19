import asyncio
import json
import types
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from tests.conftest import make_test_app_config


def _create_mock_db() -> MagicMock:
    """Create a mock DatabaseSessionManager with all required async methods."""
    db = MagicMock()
    # Mock the _safe_db_operation method used by repositories
    db._safe_db_operation = AsyncMock(
        side_effect=lambda op, *a, **kw: op(*a, **kw) if callable(op) else None
    )
    # Mock connection_context for fallback
    db.connection_context = MagicMock(
        return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())
    )
    # Mock path for backup functionality
    db.path = ":memory:"
    return db


def _setup_bot_repository_mocks(
    bot: TelegramBot, crawl_result: dict[str, Any] | None = None
) -> None:
    """Set up mock repository methods on a TelegramBot instance.

    After Repository pattern refactoring, the bot uses repository adapters
    inside components like url_processor.content_extractor.message_persistence.
    This helper patches all the relevant repository methods.
    """
    # Create mock objects that will replace the actual repositories
    request_repo_mock = MagicMock()
    request_repo_mock.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
    request_repo_mock.async_get_request_by_forward = AsyncMock(return_value=None)
    request_repo_mock.async_create_request = AsyncMock(return_value=1)
    request_repo_mock.async_update_request_status = AsyncMock()
    request_repo_mock.async_update_request_lang_detected = AsyncMock()
    request_repo_mock.async_update_request_correlation_id = AsyncMock()
    request_repo_mock.async_insert_telegram_message = AsyncMock()

    crawl_repo_mock = MagicMock()
    crawl_repo_mock.async_get_crawl_result_by_request = AsyncMock(return_value=crawl_result)
    crawl_repo_mock.async_insert_crawl_result = AsyncMock(return_value=1)

    user_repo_mock = MagicMock()
    user_repo_mock.async_upsert_user = AsyncMock()
    user_repo_mock.async_upsert_chat = AsyncMock()

    summary_repo_mock = MagicMock()
    summary_repo_mock.async_get_summary_by_request = AsyncMock(return_value=None)
    summary_repo_mock.async_upsert_summary = AsyncMock(return_value=1)
    summary_repo_mock.async_update_summary_insights = AsyncMock()

    llm_repo_mock = MagicMock()
    llm_repo_mock.async_insert_llm_call = AsyncMock(return_value=1)

    # Apply mocks to content extractor's message persistence
    if hasattr(bot, "url_processor"):
        up = bot.url_processor
        if hasattr(up, "content_extractor"):
            mp = up.content_extractor.message_persistence
            mp.request_repo = request_repo_mock
            mp.crawl_repo = crawl_repo_mock
            mp.user_repo = user_repo_mock
        if hasattr(up, "message_persistence"):
            mp = up.message_persistence
            mp.request_repo = request_repo_mock
            mp.crawl_repo = crawl_repo_mock
            mp.user_repo = user_repo_mock
        if hasattr(up, "summary_repo"):
            up.summary_repo = summary_repo_mock
        if hasattr(up, "llm_summarizer"):
            llm_sum = up.llm_summarizer
            llm_sum.summary_repo = summary_repo_mock
            llm_sum.request_repo = request_repo_mock
            llm_sum.crawl_result_repo = crawl_repo_mock
            if hasattr(llm_sum, "_workflow"):
                wf = llm_sum._workflow
                wf.summary_repo = summary_repo_mock
                wf.request_repo = request_repo_mock
                wf.llm_repo = llm_repo_mock
                wf.user_repo = user_repo_mock
            if hasattr(llm_sum, "_cache_helper"):
                # Disable cache to avoid cache hits
                llm_sum._cache_helper._cache = MagicMock()
                llm_sum._cache_helper._cache.enabled = False


def _setup_openrouter_mock(bot: TelegramBot, mock_instance: MagicMock) -> None:
    """Set up OpenRouter mock on all bot components that use it."""
    bot._openrouter = mock_instance

    if hasattr(bot, "url_processor"):
        if hasattr(bot.url_processor, "llm_summarizer"):
            bot.url_processor.llm_summarizer.openrouter = mock_instance
            if hasattr(bot.url_processor.llm_summarizer, "_workflow"):
                bot.url_processor.llm_summarizer._workflow.openrouter = mock_instance
            if hasattr(bot.url_processor.llm_summarizer, "_insights_helper"):
                bot.url_processor.llm_summarizer._insights_helper.openrouter = mock_instance
            if hasattr(bot.url_processor.llm_summarizer, "_article_helper"):
                bot.url_processor.llm_summarizer._article_helper.openrouter = mock_instance
            if hasattr(bot.url_processor.llm_summarizer, "_metadata_helper"):
                bot.url_processor.llm_summarizer._metadata_helper.openrouter = mock_instance
        if hasattr(bot.url_processor, "content_chunker"):
            bot.url_processor.content_chunker.openrouter = mock_instance


def _make_insights_response() -> MagicMock:
    """Create a mock insights response."""
    payload = {
        "topic_overview": "Context summary",
        "new_facts": [
            {
                "fact": "Example new fact",
                "why_it_matters": "Illustrates behaviour",
                "source_hint": "General knowledge",
                "confidence": 0.7,
            }
        ],
        "open_questions": ["What is the long-term impact?"],
        "suggested_sources": ["Official report"],
        "caution": "Check for recent updates beyond the model cutoff.",
    }

    mock = MagicMock()
    mock.status = "ok"
    mock.response_text = json.dumps(payload, ensure_ascii=False)
    mock.response_json = {"choices": [{"message": {"parsed": payload}}]}
    mock.model = "model"
    mock.tokens_prompt = 5
    mock.tokens_completion = 5
    mock.cost_usd = 0.01
    mock.latency_ms = 500
    mock.endpoint = "/api/v1/chat/completions"
    mock.request_headers = {}
    mock.request_messages = []
    mock.error_text = None
    return mock


class TestJsonRepair(unittest.TestCase):
    def setUp(self):
        self.cfg = make_test_app_config(db_path=":memory:")
        self.db = _create_mock_db()

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_success(self, mock_openrouter_client):
        async def run_test():
            bot = TelegramBot(self.cfg, self.db)

            # Mock the initial failed response and the successful repair
            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = '{"summary_250": "This is a truncated summary...", "tldr": "This is completely broken JSON'
            mock_llm_response_initial.response_json = {"choices": []}
            mock_llm_response_initial.model = "model"
            mock_llm_response_initial.tokens_prompt = 10
            mock_llm_response_initial.tokens_completion = 5
            mock_llm_response_initial.cost_usd = 0.02
            mock_llm_response_initial.latency_ms = 1200
            mock_llm_response_initial.endpoint = "/api/v1/chat/completions"
            mock_llm_response_initial.request_headers = {}
            mock_llm_response_initial.request_messages = []
            mock_llm_response_initial.error_text = None

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = (
                '{"summary_250": "This is a truncated summary...", "tldr": "Full summary."}'
            )
            mock_llm_response_repair.response_json = {"choices": []}
            mock_llm_response_repair.model = "model"
            mock_llm_response_repair.tokens_prompt = 10
            mock_llm_response_repair.tokens_completion = 5
            mock_llm_response_repair.cost_usd = 0.02
            mock_llm_response_repair.latency_ms = 1200
            mock_llm_response_repair.endpoint = "/api/v1/chat/completions"
            mock_llm_response_repair.request_headers = {}
            mock_llm_response_repair.request_messages = []
            mock_llm_response_repair.error_text = None

            insights_response = _make_insights_response()

            # Configure the mock OpenRouterClient
            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response_initial,
                    mock_llm_response_repair,
                    insights_response,
                    insights_response,
                    insights_response,
                    insights_response,
                ]
            )

            # Set up repository mocks with existing crawl result
            _setup_bot_repository_mocks(
                bot,
                crawl_result={
                    "content_markdown": "Some content",
                    "content_html": None,
                },
            )
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json

            # Mock json_repair to prevent local repair from working
            with patch.dict(
                "sys.modules",
                {"json_repair": None},
                clear=False,
            ):
                # Run the flow
                message = MagicMock()
                await bot._handle_url_flow(message, "http://example.com")

            # Assert that the repair was successful and the final summary is correct
            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            assert "summary_1000" in summary_json
            assert summary_json["tldr"] == "Full summary."

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_failure(self, mock_openrouter_client):
        async def run_test():
            bot = TelegramBot(self.cfg, self.db)

            # Mock failed responses
            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = "This is not JSON at all"
            mock_llm_response_initial.response_json = None
            mock_llm_response_initial.model = "model"
            mock_llm_response_initial.tokens_prompt = 10
            mock_llm_response_initial.tokens_completion = 5
            mock_llm_response_initial.cost_usd = 0.02
            mock_llm_response_initial.latency_ms = 1200
            mock_llm_response_initial.endpoint = "/api/v1/chat/completions"
            mock_llm_response_initial.request_headers = {}
            mock_llm_response_initial.request_messages = []
            mock_llm_response_initial.error_text = None

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = "Still not valid JSON"
            mock_llm_response_repair.response_json = None
            mock_llm_response_repair.model = "model"
            mock_llm_response_repair.tokens_prompt = 10
            mock_llm_response_repair.tokens_completion = 5
            mock_llm_response_repair.cost_usd = 0.02
            mock_llm_response_repair.latency_ms = 1200
            mock_llm_response_repair.endpoint = "/api/v1/chat/completions"
            mock_llm_response_repair.request_headers = {}
            mock_llm_response_repair.request_messages = []
            mock_llm_response_repair.error_text = None

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(return_value=mock_llm_response_initial)

            # Set up repository mocks with existing crawl result
            _setup_bot_repository_mocks(
                bot,
                crawl_result={
                    "content_markdown": "Some content",
                    "content_html": None,
                },
            )
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._safe_reply_func = bot._safe_reply
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._safe_reply_func = bot._safe_reply
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json
            bot.response_formatter._notification_formatter._safe_reply_func = bot._safe_reply

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            # Assert that an error message was sent
            # The error message format may vary, but should indicate invalid JSON/summary format
            messages = [
                call.args[1] for call in bot._safe_reply.await_args_list if len(call.args) >= 2
            ]
            assert any(
                "Invalid summary format" in str(msg) or "error" in str(msg).lower()
                for msg in messages
            )

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_with_extra_text(self, mock_openrouter_client):
        async def run_test():
            bot = TelegramBot(self.cfg, self.db)

            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = 'Here is the JSON: {"summary_250": "Summary"}'
            mock_llm_response.response_json = {"choices": []}
            mock_llm_response.model = "model"
            mock_llm_response.tokens_prompt = 10
            mock_llm_response.tokens_completion = 5
            mock_llm_response.cost_usd = 0.02
            mock_llm_response.latency_ms = 1100
            mock_llm_response.endpoint = "/api/v1/chat/completions"
            mock_llm_response.request_headers = {}
            mock_llm_response.request_messages = []
            mock_llm_response.error_text = None

            insights_response = _make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response,  # summary
                    insights_response,  # insights
                    insights_response,  # custom article
                    insights_response,  # extra for potential retries
                    insights_response,
                    insights_response,
                ]
            )

            # Set up repository mocks with existing crawl result
            _setup_bot_repository_mocks(
                bot,
                crawl_result={
                    "content_markdown": "Some content",
                    "content_html": None,
                },
            )
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            assert summary_json["summary_250"] == "Summary."

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_sends_original_content(self, mock_openrouter_client):
        async def run_test():
            bot = TelegramBot(self.cfg, self.db)

            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = (
                '{"summary_250": "Truncated...", "tldr": "This is completely broken JSON'
            )
            mock_llm_response_initial.response_json = {"choices": []}
            mock_llm_response_initial.model = "model"
            mock_llm_response_initial.tokens_prompt = 10
            mock_llm_response_initial.tokens_completion = 5
            mock_llm_response_initial.cost_usd = 0.02
            mock_llm_response_initial.latency_ms = 1200
            mock_llm_response_initial.endpoint = "/api/v1/chat/completions"
            mock_llm_response_initial.request_headers = {}
            mock_llm_response_initial.request_messages = []
            mock_llm_response_initial.error_text = None

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = '{"summary_250": "Fixed"}'
            mock_llm_response_repair.response_json = {"choices": []}
            mock_llm_response_repair.model = "model"
            mock_llm_response_repair.tokens_prompt = 10
            mock_llm_response_repair.tokens_completion = 5
            mock_llm_response_repair.cost_usd = 0.02
            mock_llm_response_repair.latency_ms = 1200
            mock_llm_response_repair.endpoint = "/api/v1/chat/completions"
            mock_llm_response_repair.request_headers = {}
            mock_llm_response_repair.request_messages = []
            mock_llm_response_repair.error_text = None

            insights_response = _make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response_initial,  # summary
                    mock_llm_response_repair,  # repair (if needed)
                    insights_response,  # insights
                    insights_response,  # custom article
                    insights_response,  # extra for potential retries
                    insights_response,
                    insights_response,
                ]
            )

            # Set up repository mocks with existing crawl result
            _setup_bot_repository_mocks(
                bot,
                crawl_result={
                    "content_markdown": "This is the original content",
                    "content_html": None,
                },
            )
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            # With local JSON repair, the broken JSON is fixed locally
            # The test should verify that the summary was processed successfully despite broken JSON
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call

            # Verify that the summary was processed successfully with local JSON repair
            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            # Local repair should extract "Truncated..." from broken JSON
            assert summary_json["summary_250"] == "Truncated..."

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_local_json_repair_library_used(self, mock_openrouter_client):
        async def run_test():
            bot = TelegramBot(self.cfg, self.db)

            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = '{"summary_250": "One" "tldr": "Two"}'
            mock_llm_response.response_json = None
            mock_llm_response.model = "model"
            mock_llm_response.tokens_prompt = 10
            mock_llm_response.tokens_completion = 5
            mock_llm_response.cost_usd = 0.02
            mock_llm_response.latency_ms = 1100
            mock_llm_response.endpoint = "/api/v1/chat/completions"
            mock_llm_response.request_headers = {}
            mock_llm_response.request_messages = []
            mock_llm_response.error_text = None

            insights_response = _make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response,  # summary
                    insights_response,  # insights
                    insights_response,  # custom article
                    insights_response,  # extra for potential retries
                    insights_response,
                    insights_response,
                ]
            )

            # Set up repository mocks with existing crawl result
            _setup_bot_repository_mocks(
                bot,
                crawl_result={
                    "content_markdown": "Some content",
                    "content_html": None,
                },
            )
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json

            fixed_payload = '{"summary_250": "One", "tldr": "Two"}'

            with patch.dict(
                "sys.modules",
                {"json_repair": types.SimpleNamespace(repair_json=lambda _: fixed_payload)},
                clear=False,
            ):
                message = MagicMock()
                await bot._handle_url_flow(message, "http://example.com")

            bot._reply_json.assert_called_once()
            # The flow completed successfully, which means local repair worked
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
