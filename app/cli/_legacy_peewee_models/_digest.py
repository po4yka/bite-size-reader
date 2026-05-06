"""Channel digest models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.cli._legacy_peewee_models._base import BaseModel, _utcnow
from app.cli._legacy_peewee_models._core import LLMCall, User


class Channel(BaseModel):
    """A Telegram channel tracked for digest analysis."""

    id = peewee.AutoField()
    username = peewee.TextField(unique=True)
    title = peewee.TextField(null=True)
    channel_id = peewee.BigIntegerField(null=True)
    last_fetched_at = peewee.DateTimeField(null=True)
    is_active = peewee.BooleanField(default=True)
    fetch_error_count = peewee.IntegerField(default=0)
    last_error = peewee.TextField(null=True)
    description = peewee.TextField(null=True)
    member_count = peewee.IntegerField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "channels"


class ChannelCategory(BaseModel):
    """User-defined category for organising channel subscriptions."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="channel_categories", on_delete="CASCADE")
    name = peewee.TextField()
    position = peewee.IntegerField(default=0)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "channel_categories"
        indexes = ((("user", "name"), True),)


class ChannelSubscription(BaseModel):
    """Links a user to a tracked channel."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="channel_subscriptions", on_delete="CASCADE")
    channel = peewee.ForeignKeyField(Channel, backref="subscriptions", on_delete="CASCADE")
    category = peewee.ForeignKeyField(
        ChannelCategory,
        null=True,
        backref="subscriptions",
        on_delete="SET NULL",
    )
    is_active = peewee.BooleanField(default=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "channel_subscriptions"
        indexes = ((("user", "channel"), True),)


class ChannelPost(BaseModel):
    """A single post fetched from a tracked channel."""

    id = peewee.AutoField()
    channel = peewee.ForeignKeyField(Channel, backref="posts", on_delete="CASCADE")
    message_id = peewee.IntegerField()
    text = peewee.TextField()
    media_type = peewee.TextField(null=True)
    date = peewee.DateTimeField()
    views = peewee.IntegerField(null=True)
    forwards = peewee.IntegerField(null=True)
    url = peewee.TextField(null=True)
    analyzed_at = peewee.DateTimeField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "channel_posts"
        indexes = (
            (("channel", "message_id"), True),
            (("date",), False),
        )


class ChannelPostAnalysis(BaseModel):
    """Lightweight LLM analysis result for a channel post."""

    id = peewee.AutoField()
    post = peewee.ForeignKeyField(ChannelPost, backref="analysis", unique=True, on_delete="CASCADE")
    real_topic = peewee.TextField()
    tldr = peewee.TextField()
    key_insights = JSONField(null=True)
    relevance_score = peewee.FloatField(default=0.5)
    content_type = peewee.TextField(default="other")
    llm_call = peewee.ForeignKeyField(
        LLMCall,
        backref="digest_analyses",
        null=True,
        on_delete="SET NULL",
    )
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "channel_post_analyses"


class DigestDelivery(BaseModel):
    """Record of a digest delivered to a user."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="digest_deliveries", on_delete="CASCADE")
    delivered_at = peewee.DateTimeField(default=_utcnow)
    post_count = peewee.IntegerField(default=0)
    channel_count = peewee.IntegerField(default=0)
    digest_type = peewee.TextField()
    correlation_id = peewee.TextField(null=True)
    posts_json = JSONField(null=True)

    class Meta:
        table_name = "digest_deliveries"
        indexes = (
            (("user",), False),
            (("delivered_at",), False),
        )


class UserDigestPreference(BaseModel):
    """Per-user digest preference overrides."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(
        User,
        backref="digest_preferences",
        unique=True,
        on_delete="CASCADE",
    )
    delivery_time = peewee.TextField(null=True)
    timezone = peewee.TextField(null=True)
    hours_lookback = peewee.IntegerField(null=True)
    max_posts_per_digest = peewee.IntegerField(null=True)
    min_relevance_score = peewee.FloatField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_digest_preferences"
