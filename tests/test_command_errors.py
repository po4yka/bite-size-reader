import os
import tempfile
import unittest
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
        self.id = 999
        self.message_id = 999

    async def reply_text(self, text):
        self._replies.append(text)


class BoomBot(TelegramBot):
    async def _handle_url_flow(self, message, url_text: str, **_: object):
        msg = "boom"
        raise RuntimeError(msg)


def make_bot(tmp_path: str) -> BoomBot:
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1,)),
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
        youtube=YouTubeConfig(),
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
        return BoomBot(cfg=cfg, db=db)


class TestCommandErrors(unittest.IsolatedAsyncioTestCase):
    async def test_error_during_summarize_reports_to_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/summarize https://example.com")
            await bot._on_message(msg)
            assert any("error" in r.lower() for r in msg._replies)


if __name__ == "__main__":
    unittest.main()
