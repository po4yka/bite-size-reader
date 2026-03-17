"""Tests for DigestHandler (subscribe / unsubscribe commands)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import peewee
import pytest

from app.adapters.telegram.command_handlers.digest_handler import DigestHandler
from app.adapters.telegram.command_handlers.execution_context import (
    CommandExecutionContext,
)
from app.db.models import Channel, ChannelSubscription, User, database_proxy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_UID = 111222333


def _make_config(*, enabled: bool = True, max_channels: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        digest=SimpleNamespace(enabled=enabled, max_channels=max_channels),
    )


def _make_ctx(text: str = "/subscribe", uid: int = _TEST_UID) -> CommandExecutionContext:
    """Build a minimal CommandExecutionContext for testing."""
    message = MagicMock()
    message.chat.id = 1
    return CommandExecutionContext(
        message=message,
        text=text,
        uid=uid,
        chat_id=1,
        correlation_id="test-cid-001",
        interaction_id=1,
        start_time=time.time(),
        user_repo=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=MagicMock(),
    )


async def _run_operation_directly(operation: Any, *args: Any, **kwargs: Any) -> Any:
    """Execute a DB operation directly (for in-memory SQLite tests)."""
    # Strip keyword-only args that _safe_db_transaction accepts
    kwargs.pop("operation_name", None)
    kwargs.pop("timeout", None)
    return operation(*args, **kwargs)


def _make_handler(
    *, enabled: bool = True, max_channels: int = 10
) -> tuple[DigestHandler, AsyncMock]:
    """Return (handler, safe_reply_mock)."""
    cfg = _make_config(enabled=enabled, max_channels=max_channels)
    formatter = MagicMock()
    formatter.safe_reply = AsyncMock()
    db_session = MagicMock()
    db_session._safe_db_transaction = AsyncMock(side_effect=_run_operation_directly)
    handler = DigestHandler(cfg=cast("Any", cfg), db=db_session, response_formatter=formatter)
    return handler, formatter.safe_reply


def _ensure_user(uid: int = _TEST_UID) -> User:
    """Create a User row so foreign-key constraints are satisfied."""
    user, _ = User.get_or_create(telegram_user_id=uid)
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MODELS = [User, Channel, ChannelSubscription]


@pytest.fixture(autouse=True)
def _setup_db():
    """Bind models to an in-memory SQLite database for each test."""
    test_db = peewee.SqliteDatabase(":memory:")
    database_proxy.initialize(test_db)
    test_db.connect()
    test_db.create_tables(_MODELS)
    yield
    test_db.drop_tables(_MODELS)
    test_db.close()


# ===========================================================================
# handle_subscribe
# ===========================================================================


class TestHandleSubscribe:
    """Tests for DigestHandler.handle_subscribe."""

    @pytest.mark.asyncio
    async def test_digest_disabled_replies_not_enabled(self) -> None:
        handler, reply = _make_handler(enabled=False)
        ctx = _make_ctx("/subscribe @testchannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "not enabled" in reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_no_argument_replies_usage(self) -> None:
        handler, reply = _make_handler()
        ctx = _make_ctx("/subscribe")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Usage" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_invalid_username_replies_validation_error(self) -> None:
        handler, reply = _make_handler()
        ctx = _make_ctx("/subscribe ab")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Invalid channel username" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_subscribe_not_limited_by_max_channels_config(self) -> None:
        _ensure_user()
        handler, reply = _make_handler(max_channels=1)

        # Even with DIGEST_MAX_CHANNELS=1, subscriptions remain unlimited.
        ch = Channel.create(username="existingchan", title="existingchan", is_active=True)
        ChannelSubscription.create(user=_TEST_UID, channel=ch, is_active=True)

        ctx = _make_ctx("/subscribe @anotherchannel")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @anotherchannel" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_already_subscribed_active(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()

        ch = Channel.create(username="mychannel", title="mychannel", is_active=True)
        ChannelSubscription.create(user=_TEST_UID, channel=ch, is_active=True)

        ctx = _make_ctx("/subscribe @mychannel")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Already subscribed" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_reactivation_of_inactive_subscription(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()

        ch = Channel.create(username="pausedchan", title="pausedchan", is_active=True)
        sub = ChannelSubscription.create(user=_TEST_UID, channel=ch, is_active=False)
        original_updated = sub.updated_at

        ctx = _make_ctx("/subscribe @pausedchan")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Reactivated" in reply.call_args[0][1]

        sub_refreshed = ChannelSubscription.get_by_id(sub.id)
        assert sub_refreshed.is_active is True
        # After refresh from in-memory SQLite the datetime may come back as
        # a string, so compare string representations for robustness.
        assert str(sub_refreshed.updated_at) >= str(original_updated)

    @pytest.mark.asyncio
    async def test_new_subscription_created(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()
        ctx = _make_ctx("/subscribe @newchannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @newchannel" in reply.call_args[0][1]

        # Verify DB state
        ch = Channel.get(Channel.username == "newchannel")
        sub = ChannelSubscription.get(
            ChannelSubscription.user == _TEST_UID,
            ChannelSubscription.channel == ch,
        )
        assert sub.is_active is True

    @pytest.mark.asyncio
    async def test_tme_link_normalizes_and_subscribes(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()
        ctx = _make_ctx("/subscribe https://t.me/LinkChannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @linkchannel" in reply.call_args[0][1]

        # Channel stored as lowercase
        assert Channel.get_or_none(Channel.username == "linkchannel") is not None


# ===========================================================================
# handle_unsubscribe
# ===========================================================================


class TestHandleUnsubscribe:
    """Tests for DigestHandler.handle_unsubscribe."""

    @pytest.mark.asyncio
    async def test_no_argument_replies_usage(self) -> None:
        handler, reply = _make_handler()
        ctx = _make_ctx("/unsubscribe")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Usage" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_invalid_username_replies_validation_error(self) -> None:
        handler, reply = _make_handler()
        ctx = _make_ctx("/unsubscribe xy")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Invalid channel username" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_channel_not_found(self) -> None:
        handler, reply = _make_handler()
        ctx = _make_ctx("/unsubscribe @nonexistent")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "not found" in reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_not_subscribed(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()

        # Channel exists but user has no subscription.
        Channel.create(username="orphanchan", title="orphanchan", is_active=True)

        ctx = _make_ctx("/unsubscribe @orphanchan")
        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Not subscribed" in reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_successful_unsubscribe(self) -> None:
        _ensure_user()
        handler, reply = _make_handler()

        ch = Channel.create(username="removeme", title="removeme", is_active=True)
        sub = ChannelSubscription.create(user=_TEST_UID, channel=ch, is_active=True)

        ctx = _make_ctx("/unsubscribe @removeme")
        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Unsubscribed from @removeme" in reply.call_args[0][1]

        sub_refreshed = ChannelSubscription.get_by_id(sub.id)
        assert sub_refreshed.is_active is False
