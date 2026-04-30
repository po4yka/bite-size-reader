"""Phase 3 migration contracts for generic signal-source tables."""

from __future__ import annotations

import datetime as dt
import importlib

from app.core.time_utils import UTC
from app.db.models import (
    Channel,
    ChannelPost,
    ChannelSubscription,
    FeedItem,
    RSSFeed,
    RSSFeedItem,
    RSSFeedSubscription,
    Source,
    Subscription,
    User,
)
from app.db.session import DatabaseSessionManager

migration = importlib.import_module("app.cli.migrations.015_add_signal_sources")


def test_signal_source_migration_backfills_legacy_rss_and_channel_rows(tmp_path):
    db = DatabaseSessionManager(str(tmp_path / "phase3.db"))
    db.migrate()

    with db.database.connection_context():
        user = User.create(telegram_user_id=1001, username="owner")
        rss = RSSFeed.create(
            url="https://example.com/feed.xml",
            title="Example RSS",
            site_url="https://example.com",
            description="RSS description",
        )
        RSSFeedSubscription.create(user=user, feed=rss)
        rss_item = RSSFeedItem.create(
            feed=rss,
            guid="rss-guid",
            title="RSS item",
            url="https://example.com/item",
            content="rss body",
            author="author",
            published_at=dt.datetime(2026, 4, 30, tzinfo=UTC),
        )
        channel = Channel.create(
            username="python_daily",
            title="Python Daily",
            channel_id=12345,
            description="Telegram channel",
            member_count=9000,
        )
        ChannelSubscription.create(user=user, channel=channel)
        post = ChannelPost.create(
            channel=channel,
            message_id=42,
            text="telegram body",
            media_type="text",
            date=dt.datetime(2026, 4, 30, tzinfo=UTC),
            views=100,
            forwards=7,
            url="https://t.me/python_daily/42",
        )

        # Simulate an upgraded database where the new tables exist but were not
        # populated during initial table creation.
        Source.delete().execute()
        Subscription.delete().execute()
        FeedItem.delete().execute()

        migration.upgrade(db)

        rss_source = Source.get(Source.legacy_rss_feed == rss.id)
        channel_source = Source.get(Source.legacy_channel == channel.id)
        assert rss_source.kind == "rss"
        assert rss_source.external_id == rss.url
        assert channel_source.kind == "telegram_channel"
        assert channel_source.external_id == channel.username

        assert Subscription.get(Subscription.legacy_rss_subscription == 1).source == rss_source
        assert (
            Subscription.get(Subscription.legacy_channel_subscription == 1).source
            == channel_source
        )

        assert FeedItem.get(FeedItem.legacy_rss_item == rss_item.id).canonical_url == rss_item.url
        migrated_post = FeedItem.get(FeedItem.legacy_channel_post == post.id)
        assert migrated_post.external_id == "42"
        assert migrated_post.views == 100
        assert migrated_post.forwards == 7

        assert "rss_feeds" in db.database.get_tables()
        assert "channels" in db.database.get_tables()

    db.database.close()
