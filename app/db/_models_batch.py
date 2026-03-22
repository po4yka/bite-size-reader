"""Batch-processing models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.db._models_base import BaseModel, _next_server_version, _utcnow
from app.db._models_core import Request, User


class BatchSession(BaseModel):
    """Tracks batch URL processing sessions with relationship analysis."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="batch_sessions", on_delete="CASCADE")
    correlation_id = peewee.TextField(unique=True)
    total_urls = peewee.IntegerField()
    successful_count = peewee.IntegerField(default=0)
    failed_count = peewee.IntegerField(default=0)
    relationship_type = peewee.TextField(null=True)
    relationship_confidence = peewee.FloatField(null=True)
    relationship_metadata_json = JSONField(null=True)
    combined_summary_json = JSONField(null=True)
    status = peewee.TextField(default="processing")
    analysis_status = peewee.TextField(null=True)
    processing_time_ms = peewee.IntegerField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "batch_sessions"
        indexes = (
            (("user",), False),
            (("status",), False),
            (("created_at",), False),
            (("relationship_type",), False),
        )


class BatchSessionItem(BaseModel):
    """Links batch sessions to individual requests with ordering metadata."""

    id = peewee.AutoField()
    batch_session = peewee.ForeignKeyField(BatchSession, backref="items", on_delete="CASCADE")
    request = peewee.ForeignKeyField(Request, backref="batch_item", on_delete="CASCADE")
    position = peewee.IntegerField()
    is_series_part = peewee.BooleanField(default=False)
    series_order = peewee.IntegerField(null=True)
    series_title = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "batch_session_items"
        indexes = (
            (("batch_session", "position"), False),
            (("batch_session", "request"), True),
            (("is_series_part",), False),
        )
