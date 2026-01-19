import asyncio
import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.core.json_utils import extract_json
from app.utils.json_validation import _extract_structured_dict
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

    # Apply mocks to forward processor's components
    if hasattr(bot, "forward_processor"):
        fp = bot.forward_processor
        # ForwardProcessor's own repositories
        fp.request_repo = request_repo_mock
        fp.summary_repo = summary_repo_mock
        fp.user_repo = user_repo_mock
        # ForwardContentProcessor's message persistence
        if hasattr(fp, "content_processor"):
            cp = fp.content_processor
            if hasattr(cp, "message_persistence"):
                mp = cp.message_persistence
                mp.request_repo = request_repo_mock
                mp.crawl_repo = crawl_repo_mock
                mp.user_repo = user_repo_mock
        # ForwardSummarizer's workflow
        if hasattr(fp, "summarizer"):
            if hasattr(fp.summarizer, "_workflow"):
                wf = fp.summarizer._workflow
                wf.summary_repo = summary_repo_mock
                wf.request_repo = request_repo_mock
                wf.llm_repo = llm_repo_mock
                wf.user_repo = user_repo_mock


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

    if hasattr(bot, "forward_processor"):
        fp = bot.forward_processor
        if hasattr(fp, "summarizer"):
            fp.summarizer.openrouter = mock_instance
            if hasattr(fp.summarizer, "_workflow"):
                fp.summarizer._workflow.openrouter = mock_instance
            if hasattr(fp.summarizer, "_insights_helper"):
                fp.summarizer._insights_helper.openrouter = mock_instance


class TestJsonParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = make_test_app_config(db_path=":memory:")
        self.db = _create_mock_db()

    def _make_insights_response(self) -> MagicMock:
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

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_local_repair_success(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
            bot = TelegramBot(self.cfg, self.db)

            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = '{"summary_250": "This is a truncated summary..."'
            mock_llm_response.response_json = {"choices": []}
            mock_llm_response.model = "model"
            mock_llm_response.tokens_prompt = 10
            mock_llm_response.tokens_completion = 5
            mock_llm_response.cost_usd = 0.02
            mock_llm_response.latency_ms = 1200
            mock_llm_response.endpoint = "/api/v1/chat/completions"
            mock_llm_response.request_headers = {}
            mock_llm_response.request_messages = []
            mock_llm_response.error_text = None

            insights_response = self._make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            # Provide enough responses for all async LLM calls (summary + insights + custom article + retries)
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

            # After summary flow completes, the LLM is called for:
            # 1. Summary generation
            # 2-N. Background tasks (insights, custom article, etc.)
            # The key test is that the flow completes successfully and reply_json is called
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call
            bot._reply_json.assert_called_once()

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_local_repair_failure(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
            bot = TelegramBot(self.cfg, self.db)
            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = "Still not valid JSON"

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(return_value=mock_llm_response)

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
            # Also update the notification formatter's internal reference
            bot.response_formatter._notification_formatter._safe_reply_func = bot._safe_reply

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            messages = [
                call.args[1] for call in bot._safe_reply.await_args_list if len(call.args) >= 2
            ]
            assert any("Invalid summary format" in str(msg) for msg in messages)

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_parsing_with_extra_text(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
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

            insights_response = self._make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            # Provide enough responses for all async LLM calls
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

            # The key test is that parsing extracts JSON from extra text
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call
            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            assert summary_json["summary_250"] == "Summary."
            assert "summary_1000" in summary_json

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_salvage_from_structured_error(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
            bot = TelegramBot(self.cfg, self.db)
            mock_llm_response = MagicMock()
            mock_llm_response.status = "error"
            mock_llm_response.error_text = "structured_output_parse_error"
            mock_llm_response.response_text = (
                '```json\n{"summary_250": "Fixed", "tldr": "Complete"}\n```'
            )
            mock_llm_response.model = "primary/model"
            mock_llm_response.tokens_prompt = 10
            mock_llm_response.tokens_completion = 5
            mock_llm_response.cost_usd = 0.02
            mock_llm_response.latency_ms = 1500
            mock_llm_response.request_headers = {}
            mock_llm_response.request_messages = []
            mock_llm_response.response_json = {}

            insights_response = self._make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            # Provide enough responses for all async LLM calls
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response,  # summary (error that can be salvaged)
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

            # The key test is that we can salvage from structured_output_parse_error
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call
            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            assert summary_json["summary_250"] == "Fixed."
            assert "summary_1000" in summary_json
            # Ensure we did not send the invalid summary format error
            for call_args in bot._safe_reply.await_args_list:
                if len(call_args.args) >= 2 and isinstance(call_args.args[1], str):
                    assert "Invalid summary format" not in call_args.args[1]

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_forward_salvage_from_structured_error(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
            bot = TelegramBot(self.cfg, self.db)
            mock_llm_response = MagicMock()
            mock_llm_response.status = "error"
            mock_llm_response.error_text = "structured_output_parse_error"
            mock_llm_response.response_text = (
                '```json\n{"summary_250": "Forward", "tldr": "Full"}\n```'
            )
            mock_llm_response.model = "primary/model"
            mock_llm_response.tokens_prompt = 12
            mock_llm_response.tokens_completion = 7
            mock_llm_response.cost_usd = 0.03
            mock_llm_response.latency_ms = 1200
            mock_llm_response.request_headers = {}
            mock_llm_response.request_messages = []
            mock_llm_response.response_json = {}

            insights_response = self._make_insights_response()

            mock_openrouter_instance = mock_openrouter_client.return_value
            # Provide enough responses for all async LLM calls
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response,  # summary (error that can be salvaged)
                    insights_response,  # insights
                    insights_response,  # custom article
                    insights_response,  # extra for potential retries
                    insights_response,
                    insights_response,
                ]
            )

            # Set up repository mocks (now handles forward processor too)
            _setup_bot_repository_mocks(bot, crawl_result=None)
            _setup_openrouter_mock(bot, mock_openrouter_instance)

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            # Also update the response formatter's internal references
            bot.response_formatter._reply_json_func = bot._reply_json
            bot.response_formatter._response_sender._reply_json_func = bot._reply_json

            message = MagicMock()
            message.text = "Some forwarded text"
            message.caption = None
            message.forward_from_chat = MagicMock()
            message.forward_from_chat.title = "Channel"
            message.forward_from_chat.id = 10
            message.forward_from_message_id = 20
            message.chat = MagicMock()
            message.chat.id = 5
            message.id = 123
            message.from_user = MagicMock()
            message.from_user.id = 7

            await bot._handle_forward_flow(message, correlation_id="cid", interaction_id=None)

            # The key test is that forward flow can salvage from structured_output_parse_error
            assert mock_openrouter_instance.chat.await_count >= 1  # At least summary call
            bot._reply_json.assert_called_once()
            response_payload = bot._reply_json.call_args[0][1]
            # Response is wrapped in success_response envelope with 'data' key
            summary_json = response_payload.get("data", response_payload)
            assert summary_json["summary_250"] == "Forward."

        asyncio.run(run_test())


class TestExtractJson(unittest.TestCase):
    def test_extracts_from_code_fence(self) -> None:
        payload = 'Here you go:\n```json\n{"a": 1}\n```'
        assert extract_json(payload) == {"a": 1}

    def test_balances_braces(self) -> None:
        payload = '{"a": "incomplete"'
        assert extract_json(payload) == {"a": "incomplete"}

    def test_returns_none_for_non_objects(self) -> None:
        assert extract_json("[1, 2, 3]") is None

    def test_extract_structured_dict_handles_list_response(self) -> None:
        """Test that _extract_structured_dict can handle list responses from models."""
        # Test with a list containing a valid summary dict
        list_response = [
            {
                "summary_250": "This is a short summary",
                "tldr": "This is a longer summary with more details",
                "key_ideas": ["idea1", "idea2"],
                "language": "en",
                "title": "Test Article",
            }
        ]

        result = _extract_structured_dict(list_response)
        assert result is not None
        assert isinstance(result, dict)
        assert result["summary_250"] == "This is a short summary"
        assert result["tldr"] == "This is a longer summary with more details"

        # Test with a list containing invalid items
        invalid_list_response = [{"invalid": "data"}, "string_item", 123]

        result = _extract_structured_dict(invalid_list_response)
        assert result is None

        # Test with an empty list
        empty_list: list[Any] = []
        result = _extract_structured_dict(empty_list)
        assert result is None

        # Test with a list of non-dict items
        non_dict_list = ["string", 123, True]
        result = _extract_structured_dict(non_dict_list)
        assert result is None


if __name__ == "__main__":
    unittest.main()
