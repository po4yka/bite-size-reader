import os
import tempfile
import time
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import (
    AppConfig,
    FirecrawlConfig,
    OpenRouterConfig,
    RuntimeConfig,
    TelegramConfig,
    YouTubeConfig,
)
from app.db.database import Database


class FakeMessage:
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
        self.id = 777
        self.message_id = 777

    async def reply_text(self, text: str) -> None:
        self._replies.append(text)


class SpyBot(TelegramBot):
    def __post_init__(self) -> None:
        # Mock the OpenRouter client to avoid API key validation
        with patch("app.adapters.telegram.telegram_bot.OpenRouterClient") as mock_openrouter:
            mock_openrouter.return_value = AsyncMock()
            super().__post_init__()
        self.seen_urls: list[str] = []

        # Override the URL processor to bypass Firecrawl and directly call our handler
        if hasattr(self, "url_processor"):

            async def mock_handle_url_flow(message: Any, url_text: str, **kwargs: object) -> None:
                # Track the URL and simulate successful processing
                self.seen_urls.append(url_text)
                await self._safe_reply(message, f"OK {url_text}")

            # Use setattr to avoid mypy method assignment error
            self.url_processor.handle_url_flow = mock_handle_url_flow  # type: ignore[method-assign]

    async def _handle_url_flow(self, message: Any, url_text: str, **_: object) -> None:
        self.seen_urls.append(url_text)
        await self._safe_reply(message, f"OK {url_text}")


def make_bot(tmp_path: str) -> SpyBot:
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(
            api_id=0, api_hash="", bot_token="", allowed_user_ids=(1, 55, 66, 77, 88)
        ),
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
        youtube=YouTubeConfig(),
    )
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None
    return SpyBot(cfg=cfg, db=Database(tmp_path))


class TestMultiLinks(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_and_process_multi_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            text = "Here are two links:\nhttps://a.example/a\nhttps://b.example/b"
            uid = 55
            # Send message with multiple links
            await bot._on_message(FakeMessage(text, uid=uid))
            # Bot should keep pending state
            assert uid in bot._pending_multi_links
            # Confirm
            await bot._on_message(FakeMessage("yes", uid=uid))
            assert "https://a.example/a" in bot.seen_urls
            assert "https://b.example/b" in bot.seen_urls

    async def test_cancel_multi_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            text = "https://a.example/a\nhttps://b.example/b\nhttps://a.example/a"  # duplicate should dedupe
            uid = 66
            await bot._on_message(FakeMessage(text, uid=uid))
            assert uid in bot._pending_multi_links
            await bot._on_message(FakeMessage("no", uid=uid))
            assert uid not in bot._pending_multi_links
            assert bot.seen_urls == []

    async def test_document_file_processing(self):
        """Test processing of .txt file containing URLs."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))

            # Create a test .txt file with URLs
            test_urls = [
                "https://example1.com/article1",
                "https://example2.com/article2",
                "https://example3.com/article3",
            ]

            # Create a mock document message
            class MockDocument:
                def __init__(self, file_name: str):
                    self.file_name = file_name

            class MockDocumentMessage(FakeMessage):
                def __init__(self, file_name: str, uid: int = 1):
                    super().__init__("", uid)
                    self.document = MockDocument(file_name)

                async def download(self) -> str:
                    """Mock download method that creates a temporary file."""
                    import tempfile

                    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
                        for url in test_urls:
                            f.write(f"{url}\n")
                        return f.name

            # Test processing .txt file
            msg = MockDocumentMessage("urls.txt", uid=77)
            await bot._on_message(msg)

            # Check that all URLs were processed
            assert len(bot.seen_urls) == len(test_urls)
            for url in test_urls:
                assert url in bot.seen_urls

    async def test_invalid_document_file(self):
        """Test handling of non-.txt files."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))

            # Create a mock document message
            class MockDocument:
                def __init__(self, file_name: str):
                    self.file_name = file_name

            class MockDocumentMessage(FakeMessage):
                def __init__(self, file_name: str, uid: int = 1):
                    super().__init__("", uid)
                    self.document = MockDocument(file_name)

            # Test processing a different file
            msg = MockDocumentMessage("random_file.txt", uid=88)
            await bot._on_message(msg)

            # Should not process URLs (bot.seen_urls should be empty)
            assert len(bot.seen_urls) == 0

    async def test_confirm_without_pending_links(self):
        """Confirm responses should be safe when no pending state exists."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            message = FakeMessage("yes", uid=55)

            await bot.message_handler.url_handler.handle_multi_link_confirmation(
                message,
                "yes",
                55,
                correlation_id="test-cid",
                interaction_id=0,
                start_time=time.time(),
            )

            assert message._replies, "Expected a notification reply to be sent"
            assert (
                message._replies[-1]
                == "ℹ️ No pending multi-link request to confirm. Please send the links again."
            )
            assert bot.seen_urls == []


if __name__ == "__main__":
    unittest.main()
