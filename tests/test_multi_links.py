import os
import tempfile
import unittest

from app.adapters.telegram_bot import TelegramBot
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

    async def reply_text(self, text):
        self._replies.append(text)


class SpyBot(TelegramBot):
    def __post_init__(self):
        super().__post_init__()
        self.seen_urls: list[str] = []

    async def _handle_url_flow(self, message, url_text: str, **_: object):
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


if __name__ == "__main__":
    unittest.main()
