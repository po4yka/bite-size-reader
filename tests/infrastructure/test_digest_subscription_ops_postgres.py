from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.db.models import Channel, ChannelSubscription, User
from app.db.session import Database
from app.infrastructure.persistence.sqlite.digest_subscription_ops import (
    async_subscribe_channel_atomic,
    async_unsubscribe_channel_atomic,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres digest subscription tests")

    db = Database(DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    await db.migrate()
    async with db.transaction() as session:
        await session.execute(delete(ChannelSubscription))
        await session.execute(delete(Channel))
        await session.execute(delete(User))
    try:
        yield db
    finally:
        async with db.transaction() as session:
            await session.execute(delete(ChannelSubscription))
            await session.execute(delete(Channel))
            await session.execute(delete(User))
        await db.dispose()


@pytest.mark.asyncio
async def test_digest_subscription_lifecycle_uses_postgres(database: Database) -> None:
    user_id = 77701
    async with database.transaction() as session:
        session.add(User(telegram_user_id=user_id, username="digest-owner"))

    assert (
        await async_subscribe_channel_atomic(user_id, "digestchan", db=database)
    ) == "created"
    assert (
        await async_subscribe_channel_atomic(user_id, "digestchan", db=database)
    ) == "already_subscribed"
    assert (
        await async_unsubscribe_channel_atomic(user_id, "digestchan", db=database)
    ) == "unsubscribed"
    assert (
        await async_unsubscribe_channel_atomic(user_id, "digestchan", db=database)
    ) == "not_subscribed"
    assert (
        await async_subscribe_channel_atomic(user_id, "digestchan", db=database)
    ) == "reactivated"

    async with database.session() as session:
        channel = await session.scalar(select(Channel).where(Channel.username == "digestchan"))
        assert channel is not None
        subscriptions = (
            await session.execute(
                select(ChannelSubscription).where(
                    ChannelSubscription.user_id == user_id,
                    ChannelSubscription.channel_id == channel.id,
                )
            )
        ).scalars().all()

    assert len(subscriptions) == 1
    assert subscriptions[0].is_active is True


@pytest.mark.asyncio
async def test_digest_unsubscribe_missing_channel(database: Database) -> None:
    assert (
        await async_unsubscribe_channel_atomic(77702, "missingchan", db=database)
    ) == "not_found"
