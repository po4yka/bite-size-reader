import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.telegram_bot import TelegramBot
try:
    from app.db.session import DatabaseSessionManager  # type: ignore[attr-defined]
except ImportError:
    DatabaseSessionManager = None  # type: ignore[assignment,misc]
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

    async def reply_text(self, text, **kwargs):
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
        self.error_notifications: list[tuple[str, str]] = []

    async def safe_reply(self, message, text, **_kwargs):
        self.replies.append(text)

    async def send_error_notification(self, message, error_type, correlation_id, *, details=None):
        self.error_notifications.append((error_type, details or ""))


def _make_config(tmp_path: str, allowed_ids):
    return make_test_app_config(
        db_path=tmp_path,
        allowed_user_ids=tuple(allowed_ids),
    )


def make_bot(tmp_path: str, allowed_ids):
    db = DatabaseSessionManager(tmp_path)
    db.migrate()
    cfg = _make_config(tmp_path, allowed_ids)
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object
    tbmod.filters = None

    # Mock the LLM client factory to avoid API key validation
    with patch("app.adapters.openrouter.openrouter_client.OpenRouterClient") as mock_openrouter:
        mock_openrouter.return_value = AsyncMock()
        return TelegramBot(cfg=cfg, db=db)


class TestAccessControl(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.db.models import database_proxy

        self._old_proxy_obj = database_proxy.obj

    def tearDown(self):
        from app.db.models import database_proxy

        if database_proxy.obj is not self._old_proxy_obj:
            database_proxy.initialize(self._old_proxy_obj)

    async def test_denied_user_gets_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[1])
            msg = FakeMessage("/help", uid=999)
            await bot._on_message(msg)
            await bot._shutdown()
            bot.db.database.close()
            assert any("denied" in r.lower() for r in msg._replies)

    async def test_allowed_user_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[7])
            msg = FakeMessage("/help", uid=7)
            await bot._on_message(msg)
            await bot._shutdown()
            bot.db.database.close()
            assert any("commands" in r.lower() for r in msg._replies)


class TestAccessControllerBlockReset(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.db.models import database_proxy

        self._old_proxy_obj = database_proxy.obj

    def tearDown(self):
        from app.db.models import database_proxy

        if database_proxy.obj is not self._old_proxy_obj:
            database_proxy.initialize(self._old_proxy_obj)

    async def test_failed_attempts_reset_after_block_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            cfg = _make_config(db_path, allowed_ids=[1])
            db = DatabaseSessionManager(db_path)
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

                # uid is now blocked — still denied within block window
                fake_time.advance(1)
                allowed = await controller.check_access(uid, message, "cid", 0, fake_time())
                assert allowed is False

                # Advance past block window — counter resets, uid gets fresh attempts
                fake_time.advance(controller.BLOCK_DURATION_SECONDS + 1)
                allowed = await controller.check_access(uid, message, "cid", 0, fake_time())
                assert allowed is False

                # Verify the reset by confirming uid needs MAX-1 more attempts before blocking again.
                # If the counter did NOT reset, the very next call would block (MAX+1 total).
                # Instead, uid should not yet be block-notified on attempt 2 (below MAX).
                formatter.error_notifications.clear()
                fake_time.advance(1)
                allowed = await controller.check_access(uid, message, "cid", 0, fake_time())
                assert allowed is False
                block_notifs = [
                    e for e, _ in formatter.error_notifications if e == "access_blocked"
                ]
                assert not block_notifs, "uid should not be re-blocked after just 2 fresh attempts"

    async def test_stale_tracking_state_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "app.db")
            cfg = _make_config(db_path, allowed_ids=[1])
            db = DatabaseSessionManager(db_path)
            db.migrate()
            formatter = DummyFormatter()
            controller = AccessController(cfg, db, formatter, lambda *args, **kwargs: None)
            controller.BLOCK_DURATION_SECONDS = 10
            controller.DENY_NOTIFICATION_COOLDOWN_SECONDS = 10

            stale_uid = 999
            fake_time = FakeTime(1)

            # Accumulate 2 failed attempts at early time (fewer than MAX_FAILED_ATTEMPTS)
            with patch("app.adapters.telegram.access_controller.time.time", fake_time):
                await controller.check_access(
                    stale_uid, FakeMessage("/help", uid=stale_uid), "cid", 0, 0.0
                )
                fake_time.advance(0.5)
                await controller.check_access(
                    stale_uid, FakeMessage("/help", uid=stale_uid), "cid", 0, 0.0
                )

            # Advance far past the stale window (BLOCK_DURATION_SECONDS=10)
            fake_time.value = 20

            with patch("app.adapters.telegram.access_controller.time.time", fake_time):
                # Trigger cleanup via an allowed user call
                allowed = await controller.check_access(
                    1, FakeMessage("/help", uid=1), "cid", 0, 0.0
                )
                assert allowed is True

                # Verify stale tracking was reclaimed: stale_uid should need MAX fresh attempts
                # to be blocked. Without reclaim, old 2 + 1 new = MAX → blocked immediately.
                formatter.error_notifications.clear()
                fake_time.advance(1)
                result = await controller.check_access(
                    stale_uid, FakeMessage("/help", uid=stale_uid), "cid", 0, 0.0
                )
                assert result is False  # Still denied (not in allowed list)
                block_notifs = [
                    e for e, _ in formatter.error_notifications if e == "access_blocked"
                ]
                assert not block_notifs, (
                    "stale_uid should not be blocked on first fresh attempt after cleanup"
                )


if __name__ == "__main__":
    unittest.main()
