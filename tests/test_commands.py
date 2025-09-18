import os
import tempfile
import unittest
from typing import Any

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
        self.id = 123
        self.message_id = 123

    async def reply_text(self, text: str) -> None:
        self._replies.append(text)


class BotSpy(TelegramBot):
    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.seen_urls: list[str] = []

    async def _handle_url_flow(self, message: Any, url_text: str, **_: object) -> None:
        self.seen_urls.append(url_text)
        await self._safe_reply(message, f"OK {url_text}")


def make_bot(tmp_path: str) -> BotSpy:
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
    return BotSpy(cfg=cfg, db=db)


class TestCommands(unittest.IsolatedAsyncioTestCase):
    async def test_help(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/help")
            await bot._on_message(msg)
            self.assertTrue(any("Commands" in r for r in msg._replies))

    async def test_summarize_same_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            url = "https://example.com/a"
            msg = FakeMessage(f"/summarize {url}")
            await bot._on_message(msg)
            self.assertIn(url, bot.seen_urls)

    async def test_summarize_next_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            uid = 42
            await bot._on_message(FakeMessage("/summarize", uid=uid))
            self.assertIn(uid, bot._awaiting_url_users)
            url = "https://example.com/b"
            await bot._on_message(FakeMessage(url, uid=uid))
            self.assertIn(url, bot.seen_urls)
            self.assertNotIn(uid, bot._awaiting_url_users)

    async def test_dbinfo_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            bot = make_bot(db_path)
            request_id = bot.db.create_request(
                type_="url",
                status="completed",
                correlation_id="cid",
                chat_id=1,
                user_id=1,
                input_url="https://example.com",
            )
            bot.db.insert_summary(request_id=request_id, lang="en", json_payload="{}")
            bot.db.insert_audit_log(level="INFO", event="test", details_json="{}")

            msg = FakeMessage("/dbinfo")
            await bot._on_message(msg)
            self.assertTrue(any("Database Overview" in reply for reply in msg._replies))
            self.assertTrue(any("Requests by status" in reply for reply in msg._replies))
            self.assertTrue(any("Totals" in reply for reply in msg._replies))


if __name__ == "__main__":
    unittest.main()
