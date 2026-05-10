"""Tests for DigestHandler (subscribe / unsubscribe commands)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.adapters.telegram.command_handlers.digest_handler import DigestHandler
from app.adapters.telegram.command_handlers.execution_context import (
    CommandExecutionContext,
)
from app.db.models import Channel, ChannelSubscription, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


_TEST_UID = 111222333


def _make_config(*, enabled: bool = True, max_channels: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        digest=SimpleNamespace(enabled=enabled, max_channels=max_channels),
    )


def _make_ctx(text: str = "/subscribe", uid: int = _TEST_UID) -> CommandExecutionContext:
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


def _make_handler(
    database: Database, *, enabled: bool = True, max_channels: int = 10
) -> tuple[DigestHandler, AsyncMock]:
    cfg = _make_config(enabled=enabled, max_channels=max_channels)
    formatter = MagicMock()
    formatter.safe_reply = AsyncMock()
    handler = DigestHandler(cfg=cast("Any", cfg), db=database, response_formatter=formatter)
    return handler, formatter.safe_reply


async def _ensure_user(session: AsyncSession, uid: int = _TEST_UID) -> User:
    existing = await session.scalar(select(User).where(User.telegram_user_id == uid))
    if existing is not None:
        return existing
    user = User(telegram_user_id=uid)
    session.add(user)
    await session.flush()
    return user


async def _create_channel(
    session: AsyncSession, *, username: str, title: str | None = None
) -> Channel:
    channel = Channel(username=username, title=title or username, is_active=True)
    session.add(channel)
    await session.flush()
    return channel


async def _create_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    channel_id: int,
    is_active: bool = True,
) -> ChannelSubscription:
    sub = ChannelSubscription(user_id=user_id, channel_id=channel_id, is_active=is_active)
    session.add(sub)
    await session.flush()
    return sub


# ===========================================================================
# handle_subscribe
# ===========================================================================


class TestHandleSubscribe:
    async def test_digest_disabled_replies_not_enabled(self, database: Database) -> None:
        handler, reply = _make_handler(database, enabled=False)
        ctx = _make_ctx("/subscribe @testchannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "not enabled" in reply.call_args[0][1].lower()

    async def test_no_argument_replies_usage(self, database: Database) -> None:
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/subscribe")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Usage" in reply.call_args[0][1]

    async def test_invalid_username_replies_validation_error(self, database: Database) -> None:
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/subscribe ab")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Invalid channel username" in reply.call_args[0][1]

    async def test_subscribe_not_limited_by_max_channels_config(
        self, database: Database, session: AsyncSession
    ) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database, max_channels=1)

        async with database.transaction() as s:
            ch = await _create_channel(s, username="existingchan")
            await _create_subscription(s, user_id=_TEST_UID, channel_id=ch.id)

        ctx = _make_ctx("/subscribe @anotherchannel")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @anotherchannel" in reply.call_args[0][1]

    async def test_already_subscribed_active(
        self, database: Database, session: AsyncSession
    ) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)

        async with database.transaction() as s:
            ch = await _create_channel(s, username="mychannel")
            await _create_subscription(s, user_id=_TEST_UID, channel_id=ch.id)

        ctx = _make_ctx("/subscribe @mychannel")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Already subscribed" in reply.call_args[0][1]

    async def test_reactivation_of_inactive_subscription(
        self, database: Database, session: AsyncSession
    ) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)

        async with database.transaction() as s:
            ch = await _create_channel(s, username="pausedchan")
            sub = await _create_subscription(
                s, user_id=_TEST_UID, channel_id=ch.id, is_active=False
            )
            sub_id = sub.id

        ctx = _make_ctx("/subscribe @pausedchan")
        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Reactivated" in reply.call_args[0][1]

        async with database.session() as s:
            sub_refreshed = await s.get(ChannelSubscription, sub_id)
        assert sub_refreshed is not None
        assert sub_refreshed.is_active is True

    async def test_new_subscription_created(
        self, database: Database, session: AsyncSession
    ) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/subscribe @newchannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @newchannel" in reply.call_args[0][1]

        async with database.session() as s:
            ch = await s.scalar(select(Channel).where(Channel.username == "newchannel"))
            assert ch is not None
            sub = await s.scalar(
                select(ChannelSubscription).where(
                    ChannelSubscription.user_id == _TEST_UID,
                    ChannelSubscription.channel_id == ch.id,
                )
            )
            assert sub is not None
            assert sub.is_active is True

    async def test_tme_link_normalizes_and_subscribes(
        self, database: Database, session: AsyncSession
    ) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/subscribe https://t.me/LinkChannel")

        await handler.handle_subscribe(ctx)

        reply.assert_awaited_once()
        assert "Subscribed to @linkchannel" in reply.call_args[0][1]

        async with database.session() as s:
            ch = await s.scalar(select(Channel).where(Channel.username == "linkchannel"))
        assert ch is not None


# ===========================================================================
# handle_unsubscribe
# ===========================================================================


class TestHandleUnsubscribe:
    async def test_no_argument_replies_usage(self, database: Database) -> None:
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/unsubscribe")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Usage" in reply.call_args[0][1]

    async def test_invalid_username_replies_validation_error(self, database: Database) -> None:
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/unsubscribe xy")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Invalid channel username" in reply.call_args[0][1]

    async def test_channel_not_found(self, database: Database) -> None:
        handler, reply = _make_handler(database)
        ctx = _make_ctx("/unsubscribe @nonexistent")

        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "not found" in reply.call_args[0][1].lower()

    async def test_not_subscribed(self, database: Database, session: AsyncSession) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)

        async with database.transaction() as s:
            await _create_channel(s, username="orphanchan")

        ctx = _make_ctx("/unsubscribe @orphanchan")
        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Not subscribed" in reply.call_args[0][1]

    async def test_successful_unsubscribe(self, database: Database, session: AsyncSession) -> None:
        await _ensure_user(session)
        await session.commit()
        handler, reply = _make_handler(database)

        async with database.transaction() as s:
            ch = await _create_channel(s, username="removeme")
            sub = await _create_subscription(s, user_id=_TEST_UID, channel_id=ch.id)
            sub_id = sub.id

        ctx = _make_ctx("/unsubscribe @removeme")
        await handler.handle_unsubscribe(ctx)

        reply.assert_awaited_once()
        assert "Unsubscribed from @removeme" in reply.call_args[0][1]

        async with database.session() as s:
            refreshed = await s.get(ChannelSubscription, sub_id)
        assert refreshed is not None
        assert refreshed.is_active is False
