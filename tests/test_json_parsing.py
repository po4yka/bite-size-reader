import asyncio
import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import AppConfig
from app.core.json_utils import extract_json
from app.db.database import Database
from app.utils.json_validation import _extract_structured_dict


class TestJsonParsing(unittest.TestCase):
    def setUp(self) -> None:
        telegram_cfg = MagicMock()
        telegram_cfg.api_id = "123"
        telegram_cfg.api_hash = "abc"
        telegram_cfg.bot_token = "token"
        telegram_cfg.allowed_user_ids = [1]

        firecrawl_cfg = MagicMock()
        firecrawl_cfg.api_key = "fc-key"
        firecrawl_cfg.max_connections = 1
        firecrawl_cfg.max_keepalive_connections = 1
        firecrawl_cfg.keepalive_expiry = 1
        firecrawl_cfg.credit_warning_threshold = 1
        firecrawl_cfg.credit_critical_threshold = 1

        openrouter_cfg = MagicMock()
        openrouter_cfg.api_key = "sk-or-v1-abc"
        openrouter_cfg.model = "model"
        openrouter_cfg.fallback_models = []
        openrouter_cfg.http_referer = "ref"
        openrouter_cfg.x_title = "title"
        openrouter_cfg.provider_order = []
        openrouter_cfg.enable_stats = False
        openrouter_cfg.max_tokens = 1024
        openrouter_cfg.top_p = 1.0
        openrouter_cfg.temperature = 0.5
        openrouter_cfg.enable_structured_outputs = True
        openrouter_cfg.structured_output_mode = "json_schema"
        openrouter_cfg.require_parameters = True
        openrouter_cfg.auto_fallback_structured = True
        openrouter_cfg.long_context_model = None

        runtime_cfg = MagicMock()
        runtime_cfg.log_level = "INFO"
        runtime_cfg.db_path = ":memory:"
        runtime_cfg.request_timeout_sec = 5
        runtime_cfg.debug_payloads = False
        runtime_cfg.log_truncate_length = 100
        runtime_cfg.preferred_lang = "en"
        runtime_cfg.max_concurrent_calls = 4

        self.cfg = AppConfig(telegram_cfg, firecrawl_cfg, openrouter_cfg, runtime_cfg)
        self.db = MagicMock(spec=Database)
        self.db.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
        self.db.async_get_crawl_result_by_request = AsyncMock(return_value=None)
        self.db.async_get_summary_by_request = AsyncMock(return_value=None)
        self.db.async_upsert_summary = AsyncMock(return_value=1)
        self.db.async_update_request_status = AsyncMock()
        self.db.async_insert_llm_call = AsyncMock()

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

    @patch("app.adapters.telegram_bot.OpenRouterClient")
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
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response, insights_response]
            )
            bot._openrouter = mock_openrouter_instance

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            self.db.async_get_request_by_dedupe_hash.return_value = None
            self.db.create_request.return_value = 1
            self.db.async_get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }
            self.db.async_get_summary_by_request.return_value = None
            self.db.async_upsert_summary.return_value = 1

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            assert (
                mock_openrouter_instance.chat.await_count == 4
            )  # 1 for summary + 3 for insights (json_schema + json_object fallback + retry)
            bot._reply_json.assert_called_once()

        asyncio.run(run_test())

    @patch("app.adapters.telegram_bot.OpenRouterClient")
    def test_local_repair_failure(self, mock_openrouter_client) -> None:
        async def run_test() -> None:
            bot = TelegramBot(self.cfg, self.db)
            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = "Still not valid JSON"

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(return_value=mock_llm_response)
            bot._openrouter = mock_openrouter_instance

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            self.db.async_get_request_by_dedupe_hash.return_value = None
            self.db.create_request.return_value = 1
            self.db.async_get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }
            self.db.async_get_summary_by_request.return_value = None

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            messages = [
                call.args[1] for call in bot._safe_reply.await_args_list if len(call.args) >= 2
            ]
            assert any("Invalid summary format" in str(msg) for msg in messages)

        asyncio.run(run_test())

    @patch("app.adapters.telegram_bot.OpenRouterClient")
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
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response, insights_response]
            )
            bot._openrouter = mock_openrouter_instance

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            self.db.async_get_request_by_dedupe_hash.return_value = None
            self.db.create_request.return_value = 1
            self.db.async_get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }
            self.db.async_get_summary_by_request.return_value = None
            self.db.async_upsert_summary.return_value = 1

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            assert (
                mock_openrouter_instance.chat.await_count == 4
            )  # 1 for summary + 3 for insights (json_schema + json_object fallback + retry)
            bot._reply_json.assert_called_once()
            summary_json = bot._reply_json.call_args[0][1]
            assert summary_json["summary_250"] == "Summary."
            assert "summary_1000" in summary_json

        asyncio.run(run_test())

    @patch("app.adapters.telegram_bot.OpenRouterClient")
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
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response, insights_response]
            )
            bot._openrouter = mock_openrouter_instance
            bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]
            self.db.async_get_request_by_dedupe_hash.return_value = None
            self.db.create_request.return_value = 1
            self.db.async_get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }
            self.db.async_get_summary_by_request.return_value = None
            self.db.async_upsert_summary.return_value = 1

            message = MagicMock()
            await bot._handle_url_flow(message, "http://example.com")

            assert (
                mock_openrouter_instance.chat.await_count == 4
            )  # 1 for summary + 3 for insights (json_schema + json_object fallback + retry)
            bot._reply_json.assert_called_once()
            summary_json = bot._reply_json.call_args[0][1]
            assert summary_json["summary_250"] == "Fixed."
            assert "summary_1000" in summary_json
            # Ensure we did not send the invalid summary format error
            for call_args in bot._safe_reply.await_args_list:
                if len(call_args.args) >= 2 and isinstance(call_args.args[1], str):
                    assert "Invalid summary format" not in call_args.args[1]

        asyncio.run(run_test())

    @patch("app.adapters.telegram_bot.OpenRouterClient")
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
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response, insights_response]
            )
            bot._openrouter = mock_openrouter_instance

            bot._safe_reply = AsyncMock()  # type: ignore[method-assign]
            bot._reply_json = AsyncMock()  # type: ignore[method-assign]

            self.db.create_request.return_value = 1
            self.db.async_upsert_summary.return_value = 1
            self.db.async_get_summary_by_request.return_value = None

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

            # Forward flow generates insights after summary, so we expect multiple calls
            assert (
                mock_openrouter_instance.chat.await_count >= 2
            )  # At least summary + insights attempts
            bot._reply_json.assert_called_once()
            summary_json = bot._reply_json.call_args[0][1]
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
