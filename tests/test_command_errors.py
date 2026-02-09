import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.db.database import Database
from tests.conftest import make_test_app_config


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

    async def reply_text(self, text, **kwargs):
        self._replies.append(text)


def make_bot(tmp_path: str) -> TelegramBot:
    db = Database(tmp_path)
    db.migrate()
    cfg = make_test_app_config(db_path=tmp_path, allowed_user_ids=(1,))
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    # Mock the OpenRouter client to avoid API key validation
    with patch("app.adapters.openrouter.openrouter_client.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return TelegramBot(cfg=cfg, db=db)  # type: ignore[arg-type]


class TestCommandErrors(unittest.IsolatedAsyncioTestCase):
    async def test_error_during_summarize_reports_to_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/summarize https://example.com")

            # Mock url_processor.handle_url_flow to raise an error
            original_handle_url_flow = bot.url_processor.handle_url_flow

            async def boom_url_flow(*args, **kwargs):
                raise RuntimeError("boom")

            bot.url_processor.handle_url_flow = boom_url_flow

            await bot._on_message(msg)
            assert any("error" in r.lower() for r in msg._replies)


if __name__ == "__main__":
    unittest.main()
