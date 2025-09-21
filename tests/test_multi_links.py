import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
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

        # Mock Firecrawl to avoid API key issues
        if hasattr(self, "_firecrawl"):

            class MockCrawlResult:
                def __init__(self):
                    self.status = "success"
                    self.markdown = "Mock content"
                    self.html = "Mock HTML"
                    self.source_url = "https://example.com"
                    self.language = "en"
                    self.http_status = 200
                    self.endpoint = "https://api.firecrawl.dev/v1/scrape"
                    self.error_text = None
                    self.options_json = '{"formats": ["markdown"]}'
                    self.correlation_id = None
                    self.content_markdown = "Mock content"
                    self.content_html = "Mock HTML"

            # Use setattr to mock the method
            setattr(self._firecrawl, "scrape_markdown", AsyncMock(return_value=MockCrawlResult()))

    async def _handle_url_flow(self, message: Any, url_text: str, **_: object) -> None:
        self.seen_urls.append(url_text)
        await self._safe_reply(message, f"OK {url_text}")


def make_bot(tmp_path: str) -> SpyBot:
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=tuple()),
        firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
        openrouter=OpenRouterConfig(
            api_key="y",
            model="m",
            fallback_models=tuple(),
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

    setattr(tbmod, "Client", object)
    setattr(tbmod, "filters", None)
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
            self.assertIn(uid, bot._pending_multi_links)
            # Confirm
            await bot._on_message(FakeMessage("yes", uid=uid))
            self.assertIn("https://a.example/a", bot.seen_urls)
            self.assertIn("https://b.example/b", bot.seen_urls)

    async def test_cancel_multi_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            text = "https://a.example/a\nhttps://b.example/b\nhttps://a.example/a"  # duplicate should dedupe
            uid = 66
            await bot._on_message(FakeMessage(text, uid=uid))
            self.assertIn(uid, bot._pending_multi_links)
            await bot._on_message(FakeMessage("no", uid=uid))
            self.assertNotIn(uid, bot._pending_multi_links)
            self.assertEqual(bot.seen_urls, [])

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
                        temp_path = f.name
                    return temp_path

            # Test processing .txt file
            msg = MockDocumentMessage("urls.txt", uid=77)
            await bot._on_message(msg)

            # Check that all URLs were processed
            self.assertEqual(len(bot.seen_urls), len(test_urls))
            for url in test_urls:
                self.assertIn(url, bot.seen_urls)

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
            self.assertEqual(len(bot.seen_urls), 0)


if __name__ == "__main__":
    unittest.main()
