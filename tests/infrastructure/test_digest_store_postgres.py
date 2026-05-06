from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from app.config.database import DatabaseConfig
from app.db.models import (
    Channel,
    ChannelCategory,
    ChannelPost,
    ChannelPostAnalysis,
    ChannelSubscription,
    DigestDelivery,
    FeedItem,
    Source,
    Subscription,
    User,
    UserDigestPreference,
)
from app.db.session import Database
from app.infrastructure.persistence.digest_store import DigestStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres digest store tests")

    db = Database(DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    await db.migrate()
    await _clear_rows(db)
    try:
        yield db
    finally:
        await _clear_rows(db)
        await db.dispose()


async def _clear_rows(db: Database) -> None:
    async with db.transaction() as session:
        await session.execute(delete(FeedItem))
        await session.execute(delete(Subscription))
        await session.execute(delete(Source))
        await session.execute(delete(ChannelPostAnalysis))
        await session.execute(delete(ChannelPost))
        await session.execute(delete(DigestDelivery))
        await session.execute(delete(UserDigestPreference))
        await session.execute(delete(ChannelSubscription))
        await session.execute(delete(ChannelCategory))
        await session.execute(delete(Channel))
        await session.execute(delete(User))


@pytest.mark.asyncio
async def test_digest_store_category_preference_and_delivery_reads(
    database: Database,
) -> None:
    user_id = 77801
    store = DigestStore(database)
    async with database.transaction() as session:
        session.add(User(telegram_user_id=user_id, username="digest-store"))
        channel = Channel(username="storechan", title="Store Channel")
        session.add(channel)
        await session.flush()
        session.add(
            ChannelSubscription(
                user_id=user_id,
                channel_id=channel.id,
                is_active=True,
            )
        )

    category = await store.async_create_category(user_id=user_id, name="News", position=1)
    assert await store.async_count_active_subscriptions_for_category(category) == 0
    assert await store.async_next_category_position(user_id) == 2

    subscription = (await store.async_list_active_subscriptions(user_id))[0]
    subscription.category_id = category.id
    await store.async_save_model(subscription)

    assert await store.async_count_active_subscriptions(user_id) == 1
    assert await store.async_count_active_subscriptions_for_category(category) == 1
    assert [item.name for item in await store.async_list_categories(user_id)] == ["News"]

    preference, created = await store.async_get_or_create_user_preference(
        user_id,
        {"delivery_time": "08:30", "timezone": "UTC"},
    )
    assert created is True
    assert preference.delivery_time == "08:30"
    preference.hours_lookback = 12
    await store.async_touch_preference(preference)

    fetched_preference = await store.async_get_user_preference(user_id)
    assert fetched_preference is not None
    assert fetched_preference.hours_lookback == 12

    await store.async_create_delivery(
        user_id=user_id,
        post_count=2,
        channel_count=1,
        digest_type="scheduled",
        correlation_id="corr-digest-store",
        post_ids=[101, 102],
    )
    assert await store.async_count_deliveries(user_id) == 1
    assert await store.async_list_delivered_message_ids(user_id) == {101, 102}
    deliveries = await store.async_list_deliveries(user_id=user_id, limit=10, offset=0)
    assert deliveries[0].correlation_id == "corr-digest-store"


@pytest.mark.asyncio
async def test_digest_store_posts_analysis_and_signal_mirror(database: Database) -> None:
    user_id = 77802
    store = DigestStore(database)
    async with database.transaction() as session:
        session.add(User(telegram_user_id=user_id, username="digest-posts"))

    channel = await store.async_get_or_create_channel("postchan", title="Posts")
    await store.async_update_channel_metadata(
        channel,
        {"description": "Post stream", "member_count": 123},
    )
    fetched_channel = await store.async_get_channel_by_username("postchan")
    assert fetched_channel is not None
    assert fetched_channel.description == "Post stream"

    await store.async_persist_posts(
        fetched_channel,
        [
            {
                "message_id": 501,
                "text": "Important channel post",
                "media_type": "text",
                "date": datetime.now(UTC) - timedelta(minutes=5),
                "views": 10,
                "forwards": 1,
                "url": "https://t.me/postchan/501",
            }
        ],
    )
    assert await store.async_count_channel_posts(fetched_channel) == 1
    post = (await store.async_list_channel_posts(fetched_channel, limit=10, offset=0))[0]
    assert post.message_id == 501

    await store.async_persist_analysis(
        {"_channel_id": fetched_channel.id, "message_id": 501},
        {
            "real_topic": "PostgreSQL",
            "tldr": "Digest store uses SQLAlchemy",
            "key_insights": ["ported"],
            "relevance_score": 0.9,
            "content_type": "news",
        },
    )
    cached = await store.async_find_cached_analysis(
        {"_channel_id": fetched_channel.id, "message_id": 501}
    )
    assert cached is not None
    assert cached["real_topic"] == "PostgreSQL"
    assert (await store.async_get_post_analysis(post)) is not None

    await store.async_mirror_posts_to_signal_sources(
        user_id=user_id,
        channel=fetched_channel,
        posts=[
            {
                "message_id": 501,
                "text": "Important channel post",
                "media_type": "text",
                "date": post.date,
                "views": 10,
                "forwards": 1,
                "url": "https://t.me/postchan/501",
            }
        ],
    )
    async with database.session() as session:
        source = await session.scalar(
            select(Source).where(
                Source.kind == "telegram_channel",
                Source.external_id == "postchan",
            )
        )
        assert source is not None
        assert source.legacy_channel_id == fetched_channel.id
        signal_subscription = await session.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.source_id == source.id,
            )
        )
        assert signal_subscription is not None
        feed_item = await session.scalar(
            select(FeedItem).where(
                FeedItem.source_id == source.id,
                FeedItem.external_id == "501",
            )
        )
        assert feed_item is not None
        assert feed_item.legacy_channel_post_id == post.id
