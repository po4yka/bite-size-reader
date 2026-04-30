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


@pytest.mark.asyncio
async def test_signal_repository_sets_user_source_active_with_ownership(repo):
    _user(1001, "owner")
    _user(2002, "other")
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")
    await repo.async_subscribe(user_id=1001, source_id=source["id"])

    assert (
        await repo.async_set_user_source_active(
            user_id=2002,
            source_id=source["id"],
            is_active=False,
        )
        is False
    )
    assert (
        await repo.async_set_user_source_active(
            user_id=1001,
            source_id=source["id"],
            is_active=False,
        )
        is True
    )

    reloaded = await repo.async_get_source(source["id"])
    assert reloaded["is_active"] is False


@pytest.mark.asyncio
async def test_signal_repository_lists_unscored_candidates_once(repo):
    _user(1001, "owner")
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")
    await repo.async_subscribe(user_id=1001, source_id=source["id"])
    item = await repo.async_upsert_feed_item(
        source_id=source["id"],
        external_id="guid-1",
        title="Candidate",
        canonical_url="https://example.com/post",
        content_text="Candidate body",
    )

    candidates = await repo.async_list_unscored_candidates()

    assert candidates == [
        {
            "user_id": 1001,
            "source_id": source["id"],
            "source_kind": "rss",
            "feed_item_id": item["id"],
            "title": "Candidate",
            "canonical_url": "https://example.com/post",
            "content_text": "Candidate body",
            "published_at": None,
            "views": None,
            "forwards": None,
            "comments": None,
        }
    ]

    await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        status="candidate",
        final_score=0.5,
    )

    assert await repo.async_list_unscored_candidates() == []


@pytest.mark.asyncio
async def test_signal_repository_records_source_backoff_and_circuit_breaker(repo):
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")

    disabled = await repo.async_record_source_fetch_error(
        source_id=source["id"],
        error="timeout",
        max_errors=2,
        base_backoff_seconds=60,
    )
    after_first = await repo.async_get_source(source["id"])
    disabled_again = await repo.async_record_source_fetch_error(
        source_id=source["id"],
        error="still timeout",
        max_errors=2,
        base_backoff_seconds=60,
    )
    after_second = await repo.async_get_source(source["id"])

    assert disabled is False
    assert after_first["fetch_error_count"] == 1
    assert after_first["last_error"] == "timeout"
    assert disabled_again is True
    assert after_second["fetch_error_count"] == 2
    assert after_second["is_active"] is False

    await repo.async_record_source_fetch_success(source["id"])
    recovered = await repo.async_get_source(source["id"])
    assert recovered["fetch_error_count"] == 0
    assert recovered["last_error"] is None
    assert recovered["is_active"] is False


@pytest.mark.asyncio
async def test_signal_repository_updates_feedback_and_hides_source(repo):
    _user(1001, "owner")
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")
    item = await repo.async_upsert_feed_item(source_id=source["id"], external_id="guid-1")
    signal = await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        status="candidate",
        final_score=0.7,
    )

    assert await repo.async_update_user_signal_status(
        user_id=1001,
        signal_id=signal["id"],
        status="liked",
    )
    signals = await repo.async_list_user_signals(1001)
    assert signals[0]["status"] == "liked"

    assert await repo.async_hide_signal_source(user_id=1001, signal_id=signal["id"])
    reloaded = await repo.async_get_source(source["id"])
    assert reloaded["is_active"] is False


@pytest.mark.asyncio
async def test_signal_repository_gets_one_user_signal_detail(repo):
    _user(1001, "owner")
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")
    item = await repo.async_upsert_feed_item(
        source_id=source["id"],
        external_id="guid-1",
        title="Signal item",
        canonical_url="https://example.com/item",
        content_text="Useful content",
    )
    signal = await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        status="liked",
        final_score=0.8,
    )

    detail = await repo.async_get_user_signal(user_id=1001, signal_id=signal["id"])

    assert detail is not None
    assert detail["id"] == signal["id"]
    assert detail["feed_item_id"] == item["id"]
    assert detail["feed_item_title"] == "Signal item"
    assert detail["feed_item_content_text"] == "Useful content"
    assert detail["feed_item_url"] == "https://example.com/item"


@pytest.mark.asyncio
async def test_signal_repository_boosts_signal_topic(repo):
    _user(1001, "owner")
    source = await repo.async_upsert_source(kind="rss", external_id="https://example.com/feed.xml")
    item = await repo.async_upsert_feed_item(source_id=source["id"], external_id="guid-1")
    topic = await repo.async_upsert_topic(user_id=1001, name="Infra", weight=1.0)
    signal = await repo.async_record_user_signal(
        user_id=1001,
        feed_item_id=item["id"],
        topic_id=topic["id"],
        status="candidate",
        final_score=0.8,
    )

    assert await repo.async_boost_signal_topic(user_id=1001, signal_id=signal["id"], increment=0.5)
    detail = await repo.async_get_user_signal(user_id=1001, signal_id=signal["id"])

    assert detail["status"] == "boosted_topic"
    assert detail["topic_name"] == "Infra"
    assert Topic.get_by_id(topic["id"]).weight == 1.5


@pytest.mark.asyncio
async def test_signal_repository_lists_source_health(repo):
    _user(1001, "owner")
    source = await repo.async_upsert_source(
        kind="rss",
        external_id="https://example.com/feed.xml",
        url="https://example.com/feed.xml",
        title="Example Feed",
    )
    await repo.async_subscribe(user_id=1001, source_id=int(source["id"]))
    await repo.async_record_source_fetch_error(
        source_id=int(source["id"]),
        error="timeout while fetching feed",
        max_errors=10,
        base_backoff_seconds=60,
    )

    rows = await repo.async_list_source_health(user_id=1001)

    assert len(rows) == 1
    assert rows[0]["id"] == source["id"]
    assert rows[0]["kind"] == "rss"
    assert rows[0]["title"] == "Example Feed"
    assert rows[0]["fetch_error_count"] == 1
    assert rows[0]["last_error"] == "timeout while fetching feed"
    assert rows[0]["subscription_active"] is True
    assert rows[0]["next_fetch_at"] is not None
