import asyncio
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.db.database import Database
from tests.conftest import make_test_app_config


class TestJsonRepair(unittest.TestCase):
    def setUp(self):
        self.cfg = make_test_app_config(db_path=":memory:")
        self.db = MagicMock(spec=Database)

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_success(self, mock_openrouter_client):
        async def run_test():
            self.bot = TelegramBot(self.cfg, self.db)
            # Mock the initial failed response and the successful repair
            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = '{"summary_250": "This is a truncated summary...", "tldr": "This is completely broken JSON'

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = (
                '{"summary_250": "This is a truncated summary...", "tldr": "Full summary."}'
            )

            # Configure the mock OpenRouterClient
            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response_initial, mock_llm_response_repair]
            )
            self.bot._openrouter = mock_openrouter_instance
            self.bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            self.bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            # Mock other dependencies
            self.bot._safe_reply = AsyncMock()
            self.bot._reply_json = AsyncMock()
            self.bot.db.get_request_by_dedupe_hash.return_value = None
            self.bot.db.create_request.return_value = 1
            self.bot.db.get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }

            # Mock json_repair to prevent local repair from working
            with patch.dict(
                "sys.modules",
                {"json_repair": None},
                clear=False,
            ):
                # Run the flow
                message = MagicMock()
                await self.bot._handle_url_flow(message, "http://example.com")

            # Assert that the repair was successful and the final summary is correct
            self.bot._reply_json.assert_called_once()
            call_args = self.bot._reply_json.call_args[0]
            summary_json = call_args[1]
            assert "summary_1000" in summary_json
            assert summary_json["tldr"] == "Full summary."

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_failure(self, mock_openrouter_client):
        async def run_test():
            self.bot = TelegramBot(self.cfg, self.db)
            # Mock two failed responses
            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = "This is not JSON at all"

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = "Still not valid JSON"

            # Add a third response for fallback model attempt
            mock_llm_response_fallback = MagicMock()
            mock_llm_response_fallback.status = "ok"
            mock_llm_response_fallback.response_text = "Fallback also fails"

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response_initial,
                    mock_llm_response_repair,
                    mock_llm_response_fallback,
                ]
            )
            self.bot._openrouter = mock_openrouter_instance
            self.bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            self.bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            self.bot._safe_reply = AsyncMock()
            self.bot.response_formatter._safe_reply_func = self.bot._safe_reply
            self.bot.db.get_request_by_dedupe_hash.return_value = None
            self.bot.db.create_request.return_value = 1
            self.bot.db.get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }

            message = MagicMock()
            await self.bot._handle_url_flow(message, "http://example.com")

            # Assert that an error message was sent
            self.bot._safe_reply.assert_any_call(
                message,
                "Invalid summary format. Error ID: unknown\n🔍 Reason: Unable to repair invalid JSON returned by the model",
            )

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_with_extra_text(self, mock_openrouter_client):
        async def run_test():
            self.bot = TelegramBot(self.cfg, self.db)
            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = 'Here is the JSON: {"summary_250": "Summary"}'

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(return_value=mock_llm_response)
            self.bot._openrouter = mock_openrouter_instance
            self.bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            self.bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            self.bot._safe_reply = AsyncMock()
            self.bot._reply_json = AsyncMock()
            self.bot.db.get_request_by_dedupe_hash.return_value = None
            self.bot.db.create_request.return_value = 1
            self.bot.db.get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }

            message = MagicMock()
            await self.bot._handle_url_flow(message, "http://example.com")

            self.bot._reply_json.assert_called_once()
            summary_json = self.bot._reply_json.call_args[0][1]
            assert summary_json["summary_250"] == "Summary."

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_json_repair_sends_original_content(self, mock_openrouter_client):
        async def run_test():
            self.bot = TelegramBot(self.cfg, self.db)
            mock_llm_response_initial = MagicMock()
            mock_llm_response_initial.status = "ok"
            mock_llm_response_initial.response_text = (
                '{"summary_250": "Truncated...", "tldr": "This is completely broken JSON'
            )

            mock_llm_response_repair = MagicMock()
            mock_llm_response_repair.status = "ok"
            mock_llm_response_repair.response_text = '{"summary_250": "Fixed"}'

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[
                    mock_llm_response_initial,
                    mock_llm_response_repair,
                    mock_llm_response_repair,
                    mock_llm_response_repair,
                    mock_llm_response_repair,
                ]
            )
            self.bot._openrouter = mock_openrouter_instance
            self.bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            self.bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            self.bot._safe_reply = AsyncMock()
            self.bot._reply_json = AsyncMock()
            self.bot.db.get_request_by_dedupe_hash.return_value = None
            self.bot.db.create_request.return_value = 1
            self.bot.db.get_crawl_result_by_request.return_value = {
                "content_markdown": "This is the original content"
            }

            message = MagicMock()
            await self.bot._handle_url_flow(message, "http://example.com")

            # With local JSON repair, the broken JSON is fixed locally and no LLM repair call is made
            # The test should verify that the summary was processed successfully despite broken JSON
            assert (
                mock_openrouter_instance.chat.call_count == 3
            )  # 1 for summary + 3 for insights (with fallbacks/retry)

            # Verify that the summary was processed successfully with local JSON repair
            self.bot._reply_json.assert_called_once()
            summary_json = self.bot._reply_json.call_args[0][1]
            assert (
                summary_json["summary_250"] == "Truncated..."
            )  # Local repair extracted this from broken JSON

        asyncio.run(run_test())

    @patch("app.adapters.telegram.bot_factory.OpenRouterClient")
    def test_local_json_repair_library_used(self, mock_openrouter_client):
        async def run_test():
            self.bot = TelegramBot(self.cfg, self.db)

            mock_llm_response = MagicMock()
            mock_llm_response.status = "ok"
            mock_llm_response.response_text = '{"summary_250": "One" "tldr": "Two"}'
            mock_llm_response.response_json = None

            # Add responses for insights generation
            mock_llm_response_insights = MagicMock()
            mock_llm_response_insights.status = "ok"
            mock_llm_response_insights.response_text = '{"insights": []}'

            mock_openrouter_instance = mock_openrouter_client.return_value
            mock_openrouter_instance.chat = AsyncMock(
                side_effect=[mock_llm_response, mock_llm_response_insights]
            )
            self.bot._openrouter = mock_openrouter_instance
            self.bot.url_processor.llm_summarizer.openrouter = mock_openrouter_instance
            self.bot.url_processor.content_chunker.openrouter = mock_openrouter_instance

            self.bot._safe_reply = AsyncMock()
            self.bot._reply_json = AsyncMock()
            self.bot.db.get_request_by_dedupe_hash.return_value = None
            self.bot.db.create_request.return_value = 1
            self.bot.db.get_crawl_result_by_request.return_value = {
                "content_markdown": "Some content"
            }

            fixed_payload = '{"summary_250": "One", "tldr": "Two"}'

            with patch.dict(
                "sys.modules",
                {"json_repair": types.SimpleNamespace(repair_json=lambda _: fixed_payload)},
                clear=False,
            ):
                message = MagicMock()
                await self.bot._handle_url_flow(message, "http://example.com")

            self.bot._reply_json.assert_called_once()
            assert (
                mock_openrouter_instance.chat.await_count == 3
            )  # 1 for summary + 2 for insights (limited by mock side_effect responses)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
