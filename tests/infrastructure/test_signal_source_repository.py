"""Phase 3 signal-source persistence contracts."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import peewee
import pytest

from app.core.time_utils import UTC
from app.db.models import (
    Channel,
    ChannelCategory,
    ChannelPost,
    ChannelSubscription,
    FeedItem,
    RSSFeed,
    RSSFeedItem,
    RSSFeedSubscription,
    Source,
    Subscription,
    Topic,
    User,
    UserSignal,
    database_proxy,
)
from app.infrastructure.persistence.sqlite.repositories.signal_source_repository import (
    SqliteSignalSourceRepositoryAdapter,
)


class _SyncSession:
    def __init__(self, db: peewee.Database) -> None:
        self.database = db

    async def async_execute(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(operation, *args)

    async def async_execute_transaction(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(operation, *args)


@pytest.fixture
def signal_db(tmp_path):
    old_db = database_proxy.obj
    db = peewee.SqliteDatabase(
        str(tmp_path / "signal_repo.db"),
        pragmas={"journal_mode": "wal", "foreign_keys": 1},
        check_same_thread=False,
    )
    database_proxy.initialize(db)
    models = [
        User,
        ChannelCategory,
        RSSFeed,
        RSSFeedSubscription,
        RSSFeedItem,
        Channel,
        ChannelSubscription,
        ChannelPost,
        Source,
        Subscription,
        FeedItem,
        Topic,
        UserSignal,
    ]
    db.bind(models, bind_refs=False, bind_backrefs=False)
    db.connect()
    db.create_tables(models)
    yield db
    db.drop_tables(list(reversed(models)))
    db.close()
    database_proxy.initialize(old_db)
    for model in models:
        model._meta.database = database_proxy


@pytest.fixture
def repo(signal_db):
    return SqliteSignalSourceRepositoryAdapter(_SyncSession(signal_db))


def _user(user_id: int, username: str) -> User:
    return User.create(telegram_user_id=user_id, username=username)


@pytest.mark.asyncio
async def test_source_subscription_item_and_signal_round_trip(repo):
    _user(1001, "owner")

    source = await repo.async_upsert_source(
        kind="rss",
        external_id="https://example.com/feed.xml",
        url="https://example.com/feed.xml",
        title="Example Feed",
        metadata={"etag": "abc"},
    )
    subscription = await repo.async_subscribe(
        user_id=1001,
        source_id=source["id"],
        topic_constraints={"include": ["python"]},
    )
    item = await repo.async_upsert_feed_item(
        source_id=source["id"],
        external_id="guid-1",
        canonical_url="https://example.com/post",
        title="A useful post",
        content_text="body",
        published_at=dt.datetime(2026, 4, 30, tzinfo=UTC),
        engagement={"score": 42, "views": 100},
    )
    topic = await repo.async_upsert_topic(
        user_id=1001,
        name="Python",
        description="Python systems work",
        weight=1.5,
    )
    signal = await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        topic_id=topic["id"],
        status="queued",
        heuristic_score=0.81,
        llm_score=None,
        final_score=0.81,
        evidence={"matched": ["python"]},
        filter_stage="heuristic",
    )

    assert source["kind"] == "rss"
    assert subscription["source"] == source["id"]
    assert item["engagement_score"] == 42
    assert topic["name"] == "Python"
    assert signal["status"] == "queued"

    subscriptions = await repo.async_list_user_subscriptions(1001)
    assert [(row["source_kind"], row["source_title"]) for row in subscriptions] == [
        ("rss", "Example Feed")
    ]

    signals = await repo.async_list_user_signals(1001)
    assert len(signals) == 1
    assert signals[0]["feed_item_title"] == "A useful post"
    assert signals[0]["topic_name"] == "Python"


@pytest.mark.asyncio
async def test_signal_repository_scopes_reads_to_user(repo):
    _user(1001, "owner")
    _user(2002, "other")
    source = await repo.async_upsert_source(kind="telegram_channel", external_id="python_daily")
    item = await repo.async_upsert_feed_item(
        source_id=source["id"],
        external_id="42",
        title="Private post",
    )
    await repo.async_subscribe(user_id=1001, source_id=source["id"])
    await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        status="candidate",
        heuristic_score=0.5,
        final_score=0.5,
        filter_stage="heuristic",
    )

    assert await repo.async_list_user_subscriptions(2002) == []
    assert await repo.async_list_user_signals(2002) == []


@pytest.mark.asyncio
async def test_signal_repository_can_disable_source(repo):
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")

    updated = await repo.async_set_source_active(source["id"], is_active=False)

    assert updated is True
    reloaded = await repo.async_get_source(source["id"])
    assert reloaded is not None
    assert reloaded["is_active"] is False
