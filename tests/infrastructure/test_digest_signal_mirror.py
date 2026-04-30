"""Digest channel posts mirrored into generic signal source tables."""

from __future__ import annotations

import datetime as dt

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
    User,
    UserSignal,
    database_proxy,
)
from app.infrastructure.persistence.sqlite.digest_store import SqliteDigestStore


@pytest.fixture
def digest_signal_db(tmp_path):
    old_db = database_proxy.obj
    db = peewee.SqliteDatabase(str(tmp_path / "digest_signal.db"), pragmas={"foreign_keys": 1})
    models = [
        User,
        ChannelCategory,
        Channel,
        ChannelSubscription,
        ChannelPost,
        RSSFeed,
        RSSFeedSubscription,
        RSSFeedItem,
        Source,
        Subscription,
        FeedItem,
        UserSignal,
    ]
    database_proxy.initialize(db)
    db.bind(models, bind_refs=False, bind_backrefs=False)
    db.connect()
    db.create_tables(models)
    yield db
    db.drop_tables(list(reversed(models)))
    db.close()
    database_proxy.initialize(old_db)
    for model in models:
        model._meta.database = database_proxy


def test_digest_store_mirrors_channel_posts_to_signal_tables(digest_signal_db) -> None:
    user = User.create(telegram_user_id=1001, username="owner")
    channel = Channel.create(username="python_daily", title="Python Daily", channel_id=123)
    ChannelSubscription.create(user=user, channel=channel)
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

    store = SqliteDigestStore()
    store.persist_posts(channel, posts)
    store.mirror_posts_to_signal_sources(user_id=1001, channel=channel, posts=posts)

    source = Source.get(Source.kind == "telegram_channel", Source.external_id == "python_daily")
    item = FeedItem.get(FeedItem.source == source, FeedItem.external_id == "42")
    subscription = Subscription.get(Subscription.source == source, Subscription.user == 1001)

    assert item.content_text == "Python release notes"
    assert item.views == 100
    assert item.forwards == 3
    assert subscription.is_active is True
