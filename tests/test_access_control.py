import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.telegram_bot import TelegramBot
from app.db.database import Database
from tests.conftest import make_test_app_config


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


class FakeTime:
    def __init__(self, start: float = 0.0) -> None:
        self.value = float(start)

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def __call__(self) -> float:
        return self.value


class DummyFormatter:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def safe_reply(self, message, text, **_kwargs):
        self.replies.append(text)


def _make_config(tmp_path: str, allowed_ids):
    return make_test_app_config(
        db_path=tmp_path,
        allowed_user_ids=tuple(allowed_ids),
    )


def make_bot(tmp_path: str, allowed_ids):
    db = Database(tmp_path)
    db.migrate()
    cfg = _make_config(tmp_path, allowed_ids)
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object  # type: ignore[misc,assignment]
    tbmod.filters = None

    # Mock the LLM client factory to avoid API key validation
    with patch("app.adapters.openrouter.openrouter_client.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return TelegramBot(cfg=cfg, db=db)  # type: ignore[arg-type]


class TestAccessControl(unittest.IsolatedAsyncioTestCase):
    async def test_denied_user_gets_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[1])
            msg = FakeMessage("/help", uid=999)
            await bot._on_message(msg)
            assert any("denied" in r.lower() for r in msg._replies)

    async def test_allowed_user_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[7])
            msg = FakeMessage("/help", uid=7)
            await bot._on_message(msg)
            assert any("commands" in r.lower() for r in msg._replies)


class TestAccessControllerBlockReset(unittest.IsolatedAsyncioTestCase):
    async def test_failed_attempts_reset_after_block_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            cfg = _make_config(db_path, allowed_ids=[1])
            db = Database(db_path)
            db.migrate()
            formatter = DummyFormatter()
            controller = AccessController(cfg, db, formatter, lambda *args, **kwargs: None)
            controller.BLOCK_DURATION_SECONDS = 10

            uid = 999
            message = FakeMessage("/help", uid=uid)
            fake_time = FakeTime()

            with patch("app.adapters.telegram.access_controller.time.time", fake_time):
                for _ in range(controller.MAX_FAILED_ATTEMPTS):
                    fake_time.advance(1)
                    allowed = await controller.check_access(uid, message, "cid", 0, fake_time())
                    assert allowed is False

                assert controller._failed_attempts[uid] == controller.MAX_FAILED_ATTEMPTS
                assert uid in controller._block_notified_until

                fake_time.advance(controller.BLOCK_DURATION_SECONDS + 1)
                allowed = await controller.check_access(uid, message, "cid", 0, fake_time())
                assert allowed is False
                assert controller._failed_attempts[uid] == 1
                assert uid not in controller._block_notified_until


if __name__ == "__main__":
    unittest.main()
