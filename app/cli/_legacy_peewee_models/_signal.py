"""Generic signal-source models for proactive triage."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.cli._legacy_peewee_models._base import BaseModel, _utcnow
from app.cli._legacy_peewee_models._core import User
from app.cli._legacy_peewee_models._digest import Channel, ChannelPost
from app.cli._legacy_peewee_models._rss import RSSFeed, RSSFeedItem, RSSFeedSubscription


class Source(BaseModel):
    """Generic source that can represent RSS feeds or Telegram channels."""

    id = peewee.AutoField()
    kind = peewee.TextField()
    external_id = peewee.TextField(null=True)
    url = peewee.TextField(null=True)
    title = peewee.TextField(null=True)
    description = peewee.TextField(null=True)
    site_url = peewee.TextField(null=True)
    is_active = peewee.BooleanField(default=True)
    fetch_error_count = peewee.IntegerField(default=0)
    last_error = peewee.TextField(null=True)
    last_fetched_at = peewee.DateTimeField(null=True)
    last_successful_at = peewee.DateTimeField(null=True)
    metadata_json = JSONField(null=True)
    legacy_rss_feed = peewee.ForeignKeyField(
        RSSFeed,
        null=True,
        unique=True,
        backref="signal_sources",
        on_delete="SET NULL",
    )
    legacy_channel = peewee.ForeignKeyField(
        Channel,
        null=True,
        unique=True,
        backref="signal_sources",
        on_delete="SET NULL",
    )
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "sources"
        indexes = (
            (("kind", "external_id"), True),
            (("kind", "is_active"), False),
        )


class Subscription(BaseModel):
    """Single-user subscription to a generic source."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="subscriptions", on_delete="CASCADE")
    source = peewee.ForeignKeyField(Source, backref="subscriptions", on_delete="CASCADE")
    is_active = peewee.BooleanField(default=True)
    cadence_seconds = peewee.IntegerField(null=True)
    next_fetch_at = peewee.DateTimeField(null=True)
    topic_constraints_json = JSONField(null=True)
    metadata_json = JSONField(null=True)
    legacy_rss_subscription = peewee.ForeignKeyField(
        RSSFeedSubscription,
        null=True,
        unique=True,
        backref="signal_subscriptions",
        on_delete="SET NULL",
    )
    legacy_channel_subscription = peewee.IntegerField(null=True, unique=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "subscriptions"
        indexes = (
            (("user", "source"), True),
            (("user", "is_active"), False),
            (("next_fetch_at",), False),
        )


class FeedItem(BaseModel):
    """Generic ingested item emitted by a source."""

    id = peewee.AutoField()
    source = peewee.ForeignKeyField(Source, backref="feed_items", on_delete="CASCADE")
    external_id = peewee.TextField()
    canonical_url = peewee.TextField(null=True)
    title = peewee.TextField(null=True)
    content_text = peewee.TextField(null=True)
    author = peewee.TextField(null=True)
    published_at = peewee.DateTimeField(null=True)
    views = peewee.IntegerField(null=True)
    forwards = peewee.IntegerField(null=True)
    comments = peewee.IntegerField(null=True)
    engagement_score = peewee.FloatField(null=True)
    metadata_json = JSONField(null=True)
    legacy_rss_item = peewee.ForeignKeyField(
        RSSFeedItem,
        null=True,
        unique=True,
        backref="signal_feed_items",
        on_delete="SET NULL",
    )
    legacy_channel_post = peewee.ForeignKeyField(
        ChannelPost,
        null=True,
        unique=True,
        backref="signal_feed_items",
        on_delete="SET NULL",
    )
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "feed_items"
        indexes = (
            (("source", "external_id"), True),
            (("published_at",), False),
            (("canonical_url",), False),
        )


class Topic(BaseModel):
    """Single-user interest topic used by signal scoring."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="signal_topics", on_delete="CASCADE")
    name = peewee.TextField()
    description = peewee.TextField(null=True)
    weight = peewee.FloatField(default=1.0)
    embedding_ref = peewee.TextField(null=True)
    metadata_json = JSONField(null=True)
    is_active = peewee.BooleanField(default=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "topics"
        indexes = (
            (("user", "name"), True),
            (("user", "is_active"), False),
        )


class UserSignal(BaseModel):
    """Per-user signal decision for an ingested feed item."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="user_signals", on_delete="CASCADE")
    feed_item = peewee.ForeignKeyField(FeedItem, backref="user_signals", on_delete="CASCADE")
    topic = peewee.ForeignKeyField(Topic, null=True, backref="signals", on_delete="SET NULL")
    status = peewee.TextField(default="candidate")
    heuristic_score = peewee.FloatField(null=True)
    llm_score = peewee.FloatField(null=True)
    final_score = peewee.FloatField(null=True)
    filter_stage = peewee.TextField(default="heuristic")
    evidence_json = JSONField(null=True)
    llm_judge_json = JSONField(null=True)
    llm_cost_usd = peewee.FloatField(null=True)
    decided_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_signals"
        indexes = (
            (("user", "feed_item"), True),
            (("user", "status"), False),
            (("final_score",), False),
        )
