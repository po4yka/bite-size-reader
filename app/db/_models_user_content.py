"""User-facing summary organization and feedback models."""

from __future__ import annotations

import peewee

from app.db._models_base import BaseModel, _next_server_version, _utcnow
from app.db._models_core import Summary, User


class SummaryFeedback(BaseModel):
    """User feedback on a summary."""

    id = peewee.UUIDField(primary_key=True)
    user = peewee.ForeignKeyField(User, backref="summary_feedbacks", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, backref="feedbacks", on_delete="CASCADE")
    rating = peewee.IntegerField(null=True)
    issues = peewee.TextField(null=True)
    comment = peewee.TextField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_feedbacks"
        indexes = ((("user", "summary"), True),)


class CustomDigest(BaseModel):
    """User-created custom digest from selected summaries."""

    id = peewee.UUIDField(primary_key=True)
    user = peewee.ForeignKeyField(User, backref="custom_digests", on_delete="CASCADE")
    title = peewee.TextField(null=True)
    summary_ids = peewee.TextField()
    format = peewee.TextField(default="markdown")
    content = peewee.TextField(null=True)
    status = peewee.TextField(default="pending")
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "custom_digests"
        indexes = (
            (("user",), False),
            (("created_at",), False),
        )


class SummaryHighlight(BaseModel):
    """User highlight on a summary's content."""

    id = peewee.UUIDField(primary_key=True)
    user = peewee.ForeignKeyField(User, backref="highlights", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, backref="highlights", on_delete="CASCADE")
    text = peewee.TextField()
    start_offset = peewee.IntegerField(null=True)
    end_offset = peewee.IntegerField(null=True)
    color = peewee.TextField(null=True)
    note = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_highlights"
        indexes = (
            (("user", "summary"), False),
            (("updated_at",), False),
        )


class UserGoal(BaseModel):
    """Reading goal per user per period type."""

    id = peewee.UUIDField(primary_key=True)
    user = peewee.ForeignKeyField(User, backref="goals", on_delete="CASCADE")
    goal_type = peewee.TextField()
    target_count = peewee.IntegerField()
    scope_type = peewee.TextField(default="global")
    scope_id = peewee.IntegerField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_goals"
        indexes = ((("user", "goal_type", "scope_type"), False),)


class Tag(BaseModel):
    """User-defined tag for organizing summaries."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="tags", on_delete="CASCADE")
    name = peewee.TextField()
    normalized_name = peewee.TextField()
    color = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "tags"
        indexes = ((("user", "normalized_name"), True),)


class SummaryTag(BaseModel):
    """Association between a summary and a tag."""

    id = peewee.AutoField()
    summary = peewee.ForeignKeyField(Summary, backref="summary_tags", on_delete="CASCADE")
    tag = peewee.ForeignKeyField(Tag, backref="summary_tags", on_delete="CASCADE")
    source = peewee.TextField(default="manual")
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_tags"
        indexes = (
            (("summary", "tag"), True),
            (("tag",), False),
        )
