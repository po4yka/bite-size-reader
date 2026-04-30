"""Add generic signal-source tables and backfill legacy RSS/channel data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
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
    Topic,
    UserSignal,
)

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_MODELS = [Source, Subscription, FeedItem, Topic, UserSignal]


def _database(db: DatabaseSessionManager) -> Any:
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)
    return db_instance


def upgrade(db: DatabaseSessionManager) -> None:
    """Create generic signal tables and backfill from existing source tables."""

    db_instance = _database(db)
    db_instance.create_tables(_MODELS, safe=True)
    rss_sources = _backfill_rss_sources()
    channel_sources = _backfill_channel_sources()
    rss_subscriptions = _backfill_rss_subscriptions()
    channel_subscriptions = _backfill_channel_subscriptions()
    rss_items = _backfill_rss_items()
    channel_items = _backfill_channel_items()
    logger.info(
        "signal_sources_migration_complete",
        extra={
            "rss_sources": rss_sources,
            "channel_sources": channel_sources,
            "rss_subscriptions": rss_subscriptions,
            "channel_subscriptions": channel_subscriptions,
            "rss_items": rss_items,
            "channel_items": channel_items,
        },
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop signal-source tables while preserving legacy RSS/channel tables."""

    db_instance = _database(db)
    db_instance.drop_tables(list(reversed(_MODELS)), safe=True)
    logger.warning("signal_sources_tables_dropped")


def _backfill_rss_sources() -> int:
    count = 0
    for feed in RSSFeed.select():
        source, created = Source.get_or_create(
            kind="rss",
            external_id=feed.url,
            defaults={
                "url": feed.url,
                "title": feed.title,
                "description": feed.description,
                "site_url": feed.site_url,
                "is_active": feed.is_active,
                "fetch_error_count": feed.fetch_error_count,
                "last_error": feed.last_error,
                "last_fetched_at": feed.last_fetched_at,
                "last_successful_at": feed.last_successful_at,
                "metadata_json": {
                    "etag": feed.etag,
                    "last_modified": feed.last_modified,
                },
                "legacy_rss_feed": feed.id,
            },
        )
        _update_source_from_rss(source, feed)
        count += int(created)
    return count


def _update_source_from_rss(source: Source, feed: RSSFeed) -> None:
    source.url = feed.url
    source.title = feed.title
    source.description = feed.description
    source.site_url = feed.site_url
    source.is_active = feed.is_active
    source.fetch_error_count = feed.fetch_error_count
    source.last_error = feed.last_error
    source.last_fetched_at = feed.last_fetched_at
    source.last_successful_at = feed.last_successful_at
    source.metadata_json = {"etag": feed.etag, "last_modified": feed.last_modified}
    source.legacy_rss_feed = feed.id
    source.save()


def _backfill_channel_sources() -> int:
    count = 0
    for channel in Channel.select():
        source, created = Source.get_or_create(
            kind="telegram_channel",
            external_id=channel.username,
            defaults={
                "url": f"https://t.me/{channel.username}",
                "title": channel.title,
                "description": channel.description,
                "is_active": channel.is_active,
                "fetch_error_count": channel.fetch_error_count,
                "last_error": channel.last_error,
                "last_fetched_at": channel.last_fetched_at,
                "metadata_json": {
                    "channel_id": channel.channel_id,
                    "member_count": channel.member_count,
                },
                "legacy_channel": channel.id,
            },
        )
        _update_source_from_channel(source, channel)
        count += int(created)
    return count


def _update_source_from_channel(source: Source, channel: Channel) -> None:
    source.url = f"https://t.me/{channel.username}"
    source.title = channel.title
    source.description = channel.description
    source.is_active = channel.is_active
    source.fetch_error_count = channel.fetch_error_count
    source.last_error = channel.last_error
    source.last_fetched_at = channel.last_fetched_at
    source.metadata_json = {"channel_id": channel.channel_id, "member_count": channel.member_count}
    source.legacy_channel = channel.id
    source.save()


def _backfill_rss_subscriptions() -> int:
    count = 0
    for legacy in RSSFeedSubscription.select():
        source = Source.get_or_none(Source.legacy_rss_feed == legacy.feed_id)
        if source is None:
            continue
        subscription, created = Subscription.get_or_create(
            user=legacy.user_id,
            source=source.id,
            defaults={
                "is_active": legacy.is_active,
                "legacy_rss_subscription": legacy.id,
                "metadata_json": {"category_id": legacy.category_id},
            },
        )
        subscription.is_active = legacy.is_active
        subscription.legacy_rss_subscription = legacy.id
        subscription.metadata_json = {"category_id": legacy.category_id}
        subscription.save()
        count += int(created)
    return count


def _backfill_channel_subscriptions() -> int:
    count = 0
    for legacy in ChannelSubscription.select():
        source = Source.get_or_none(Source.legacy_channel == legacy.channel_id)
        if source is None:
            continue
        subscription, created = Subscription.get_or_create(
            user=legacy.user_id,
            source=source.id,
            defaults={
                "is_active": legacy.is_active,
                "legacy_channel_subscription": legacy.id,
                "metadata_json": {"category_id": legacy.category_id},
            },
        )
        subscription.is_active = legacy.is_active
        subscription.legacy_channel_subscription = legacy.id
        subscription.metadata_json = {"category_id": legacy.category_id}
        subscription.save()
        count += int(created)
    return count


def _backfill_rss_items() -> int:
    count = 0
    for legacy in RSSFeedItem.select():
        source = Source.get_or_none(Source.legacy_rss_feed == legacy.feed_id)
        if source is None:
            continue
        item, created = FeedItem.get_or_create(
            source=source.id,
            external_id=legacy.guid,
            defaults={
                "canonical_url": legacy.url,
                "title": legacy.title,
                "content_text": legacy.content,
                "author": legacy.author,
                "published_at": legacy.published_at,
                "legacy_rss_item": legacy.id,
            },
        )
        item.canonical_url = legacy.url
        item.title = legacy.title
        item.content_text = legacy.content
        item.author = legacy.author
        item.published_at = legacy.published_at
        item.legacy_rss_item = legacy.id
        item.save()
        count += int(created)
    return count


def _backfill_channel_items() -> int:
    count = 0
    for legacy in ChannelPost.select():
        source = Source.get_or_none(Source.legacy_channel == legacy.channel_id)
        if source is None:
            continue
        item, created = FeedItem.get_or_create(
            source=source.id,
            external_id=str(legacy.message_id),
            defaults={
                "canonical_url": legacy.url,
                "content_text": legacy.text,
                "published_at": legacy.date,
                "views": legacy.views,
                "forwards": legacy.forwards,
                "metadata_json": {"media_type": legacy.media_type},
                "legacy_channel_post": legacy.id,
            },
        )
        item.canonical_url = legacy.url
        item.content_text = legacy.text
        item.published_at = legacy.date
        item.views = legacy.views
        item.forwards = legacy.forwards
        item.metadata_json = {"media_type": legacy.media_type}
        item.legacy_channel_post = legacy.id
        item.save()
        count += int(created)
    return count
