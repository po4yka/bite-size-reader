"""Aggregation session persistence models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.cli._legacy_peewee_models._base import BaseModel, _next_server_version, _utcnow
from app.cli._legacy_peewee_models._core import Request, User


class AggregationSession(BaseModel):
    """Tracks mixed-source aggregation bundles independently from URL batches."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="aggregation_sessions", on_delete="CASCADE")
    correlation_id = peewee.TextField(unique=True)
    total_items = peewee.IntegerField()
    successful_count = peewee.IntegerField(default=0)
    failed_count = peewee.IntegerField(default=0)
    duplicate_count = peewee.IntegerField(default=0)
    progress_percent = peewee.IntegerField(default=0)
    allow_partial_success = peewee.BooleanField(default=True)
    status = peewee.TextField(default="pending")
    bundle_metadata_json = JSONField(null=True)
    aggregation_output_json = JSONField(null=True)
    failure_code = peewee.TextField(null=True)
    failure_message = peewee.TextField(null=True)
    failure_details_json = JSONField(null=True)
    processing_time_ms = peewee.IntegerField(null=True)
    queued_at = peewee.DateTimeField(default=_utcnow, null=True)
    started_at = peewee.DateTimeField(null=True)
    completed_at = peewee.DateTimeField(null=True)
    last_progress_at = peewee.DateTimeField(default=_utcnow, null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "aggregation_sessions"
        indexes = (
            (("user",), False),
            (("status",), False),
            (("created_at",), False),
        )


class AggregationSessionItem(BaseModel):
    """Stores ordered source items and their extraction outcomes."""

    id = peewee.AutoField()
    aggregation_session = peewee.ForeignKeyField(
        AggregationSession,
        backref="items",
        on_delete="CASCADE",
    )
    request = peewee.ForeignKeyField(
        Request,
        backref="aggregation_items",
        null=True,
        on_delete="SET NULL",
    )
    position = peewee.IntegerField()
    source_kind = peewee.TextField()
    source_item_id = peewee.TextField()
    source_dedupe_key = peewee.TextField()
    original_value = peewee.TextField(null=True)
    normalized_value = peewee.TextField(null=True)
    external_id = peewee.TextField(null=True)
    telegram_chat_id = peewee.BigIntegerField(null=True)
    telegram_message_id = peewee.IntegerField(null=True)
    telegram_media_group_id = peewee.TextField(null=True)
    title_hint = peewee.TextField(null=True)
    source_metadata_json = JSONField(null=True)
    normalized_document_json = JSONField(null=True)
    extraction_metadata_json = JSONField(null=True)
    status = peewee.TextField(default="pending")
    duplicate_of_item_id = peewee.IntegerField(null=True)
    failure_code = peewee.TextField(null=True)
    failure_message = peewee.TextField(null=True)
    failure_details_json = JSONField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "aggregation_session_items"
        indexes = (
            (("aggregation_session", "position"), True),
            (("aggregation_session", "source_item_id"), False),
            (("request",), False),
            (("status",), False),
            (("duplicate_of_item_id",), False),
        )
