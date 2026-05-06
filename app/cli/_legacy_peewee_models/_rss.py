"""RSS feed models."""

from __future__ import annotations

import peewee

from app.cli._legacy_peewee_models._base import BaseModel, _utcnow
from app.cli._legacy_peewee_models._core import User
from app.cli._legacy_peewee_models._digest import ChannelCategory


class RSSFeed(BaseModel):
    """RSS/Atom feed source."""

    id = peewee.AutoField()
    url = peewee.TextField(unique=True)
    title = peewee.TextField(null=True)
    description = peewee.TextField(null=True)
    site_url = peewee.TextField(null=True)
    last_fetched_at = peewee.DateTimeField(null=True)
    last_successful_at = peewee.DateTimeField(null=True)
    fetch_error_count = peewee.IntegerField(default=0)
    last_error = peewee.TextField(null=True)
    etag = peewee.TextField(null=True)
    last_modified = peewee.TextField(null=True)
    is_active = peewee.BooleanField(default=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rss_feeds"


class RSSFeedSubscription(BaseModel):
    """User subscription to an RSS feed."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="rss_subscriptions", on_delete="CASCADE")
    feed = peewee.ForeignKeyField(RSSFeed, backref="subscriptions", on_delete="CASCADE")
    category = peewee.ForeignKeyField(ChannelCategory, null=True, on_delete="SET NULL")
    is_active = peewee.BooleanField(default=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rss_feed_subscriptions"
        indexes = ((("user", "feed"), True),)


class RSSFeedItem(BaseModel):
    """Individual item from an RSS feed."""

    id = peewee.AutoField()
    feed = peewee.ForeignKeyField(RSSFeed, backref="items", on_delete="CASCADE")
    guid = peewee.TextField()
    title = peewee.TextField(null=True)
    url = peewee.TextField(null=True)
    content = peewee.TextField(null=True)
    author = peewee.TextField(null=True)
    published_at = peewee.DateTimeField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rss_feed_items"
        indexes = (
            (("feed", "guid"), True),
            (("published_at",), False),
        )


class RSSItemDelivery(BaseModel):
    """Tracks which RSS items have been delivered to which users."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, on_delete="CASCADE")
    item = peewee.ForeignKeyField(RSSFeedItem, on_delete="CASCADE")
    summary_request_id = peewee.IntegerField(null=True)
    delivered_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rss_item_deliveries"
        indexes = ((("user", "item"), True),)
