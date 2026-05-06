"""Smoke tests for command handlers not covered by test_commands.py.

Covers OnboardingHandler (/start).
AdminHandler (/dbinfo, /dbverify) and URLCommandsHandler (/summarize)
are exercised in test_commands.py via the bot integration path.
"""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.telegram_bot import TelegramBot
try:
    from app.db.session import DatabaseSessionManager  # type: ignore[attr-defined]
except ImportError:
    DatabaseSessionManager = None  # type: ignore[assignment,misc]
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
        self.id = 200
        self.message_id = 200

    async def reply_text(self, text: str, **kwargs) -> None:
        self._replies.append(text)


def make_bot(tmp_path: str) -> TelegramBot:
    db = DatabaseSessionManager(tmp_path)
    db.migrate()
    cfg = make_test_app_config(db_path=tmp_path, allowed_user_ids=(1,))
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    with patch("app.adapters.openrouter.openrouter_client.OpenRouterClient") as mock_or:
        mock_or.return_value = AsyncMock()
        return TelegramBot(cfg=cfg, db=db)


class TestOnboardingHandler(unittest.IsolatedAsyncioTestCase):
    """Smoke tests for OnboardingHandler (/start, /help)."""

    def setUp(self):
        from app.db.models import database_proxy

        self._old_proxy_obj = database_proxy.obj

    def tearDown(self):
        from app.db.models import database_proxy

        if database_proxy.obj is not self._old_proxy_obj:
            database_proxy.initialize(self._old_proxy_obj)

    async def test_start_command_replies(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/start")
            await bot._on_message(msg)
            await bot._shutdown()
            bot.db.database.close()
            assert msg._replies, "/start should produce at least one reply"

    async def test_help_command_lists_commands(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"))
            msg = FakeMessage("/help")
            await bot._on_message(msg)
            await bot._shutdown()
            bot.db.database.close()
            assert any("Commands" in r for r in msg._replies)


if __name__ == "__main__":
    unittest.main()
