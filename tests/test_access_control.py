import os
import tempfile
import unittest

from app.adapters.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database


class FakeMessage:
    def __init__(self, text: str, uid: int):
        class _User:
            def __init__(self, id):
                self.id = id

        class _Chat:
            id = 1

        self.text = text
        self.chat = _Chat()
        self.from_user = _User(uid)
        self._replies: list[str] = []
        self.id = 101
        self.message_id = 101

    async def reply_text(self, text):
        self._replies.append(text)


def make_bot(tmp_path: str, allowed_ids):
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(
            api_id=0, api_hash="", bot_token="", allowed_user_ids=tuple(allowed_ids)
        ),
        firecrawl=FirecrawlConfig(api_key="x"),
        openrouter=OpenRouterConfig(
            api_key="y", model="m", fallback_models=tuple(), http_referer=None, x_title=None
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
    return TelegramBot(cfg=cfg, db=db)


class TestAccessControl(unittest.IsolatedAsyncioTestCase):
    async def test_denied_user_gets_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[1])
            msg = FakeMessage("/help", uid=999)
            await bot._on_message(msg)
            self.assertTrue(any("denied" in r.lower() for r in msg._replies))

    async def test_allowed_user_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[7])
            msg = FakeMessage("/help", uid=7)
            await bot._on_message(msg)
            self.assertTrue(any("commands" in r.lower() for r in msg._replies))


if __name__ == "__main__":
    unittest.main()
