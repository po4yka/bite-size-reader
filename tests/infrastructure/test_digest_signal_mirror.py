"""Digest channel posts mirrored into generic signal source tables."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.time_utils import UTC
from app.db.models import (
    Channel,
    ChannelSubscription,
    FeedItem,
    Source,
    Subscription,
    User,
)
from app.infrastructure.persistence.digest_store import DigestStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


async def test_digest_store_mirrors_channel_posts_to_signal_tables(
    database: Database, session: AsyncSession
) -> None:
    async with database.transaction() as s:
        s.add(User(telegram_user_id=1001, username="owner"))
        await s.flush()
        channel = Channel(username="python_daily", title="Python Daily", channel_id=123)
        s.add(channel)
        await s.flush()
        s.add(ChannelSubscription(user_id=1001, channel_id=channel.id))
        await s.flush()
        channel_id = channel.id

    posts = [
        {
            "message_id": 42,
            "text": "Python release notes",
            "date": dt.datetime(2026, 4, 30, tzinfo=UTC),
            "views": 100,
            "forwards": 3,
            "url": "https://t.me/python_daily/42",
            "media_type": "text",
        }
    ]

    async with database.session() as s:
        channel = await s.get(Channel, channel_id)

    store = DigestStore(database=database)
    await store.async_persist_posts(channel, posts)
    await store.async_mirror_posts_to_signal_sources(
        user_id=1001, channel=channel, posts=posts
    )

    async with database.session() as s:
        source = await s.scalar(
            select(Source).where(
                Source.kind == "telegram_channel", Source.external_id == "python_daily"
            )
        )
        assert source is not None
        item = await s.scalar(
            select(FeedItem).where(
                FeedItem.source_id == source.id, FeedItem.external_id == "42"
            )
        )
        assert item is not None
        subscription = await s.scalar(
            select(Subscription).where(
                Subscription.source_id == source.id, Subscription.user_id == 1001
            )
        )
        assert subscription is not None

    assert item.content_text == "Python release notes"
    assert item.views == 100
    assert item.forwards == 3
    assert subscription.is_active is True
