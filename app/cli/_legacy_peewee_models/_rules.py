"""Webhook, rule, import, and backup models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.cli._legacy_peewee_models._base import BaseModel, _next_server_version, _utcnow
from app.cli._legacy_peewee_models._core import Summary, User


class WebhookSubscription(BaseModel):
    """Per-user webhook endpoint subscription."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="webhooks", on_delete="CASCADE")
    name = peewee.TextField(null=True)
    url = peewee.TextField()
    secret = peewee.TextField()
    events_json = JSONField(default=list)
    enabled = peewee.BooleanField(default=True)
    status = peewee.TextField(default="active")
    failure_count = peewee.IntegerField(default=0)
    last_delivery_at = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "webhook_subscriptions"
        indexes = ((("user", "enabled"), False),)


class WebhookDelivery(BaseModel):
    """Delivery attempt log for a webhook."""

    id = peewee.AutoField()
    subscription = peewee.ForeignKeyField(
        WebhookSubscription,
        backref="deliveries",
        on_delete="CASCADE",
    )
    event_type = peewee.TextField()
    payload_json = JSONField()
    response_status = peewee.IntegerField(null=True)
    response_body = peewee.TextField(null=True)
    duration_ms = peewee.IntegerField(null=True)
    success = peewee.BooleanField()
    attempt = peewee.IntegerField(default=1)
    error = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "webhook_deliveries"
        indexes = (
            (("subscription",), False),
            (("created_at",), False),
        )


class AutomationRule(BaseModel):
    """User-defined automation rule."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="rules", on_delete="CASCADE")
    name = peewee.TextField()
    description = peewee.TextField(null=True)
    enabled = peewee.BooleanField(default=True)
    event_type = peewee.TextField()
    match_mode = peewee.TextField(default="all")
    conditions_json = JSONField(default=list)
    actions_json = JSONField(default=list)
    priority = peewee.IntegerField(default=0)
    run_count = peewee.IntegerField(default=0)
    last_triggered_at = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "automation_rules"
        indexes = (
            (("user", "enabled"), False),
            (("event_type",), False),
        )


class RuleExecutionLog(BaseModel):
    """Audit trail for rule executions."""

    id = peewee.AutoField()
    rule = peewee.ForeignKeyField(AutomationRule, backref="logs", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, null=True, on_delete="SET NULL")
    event_type = peewee.TextField()
    matched = peewee.BooleanField()
    conditions_result_json = JSONField(null=True)
    actions_taken_json = JSONField(null=True)
    error = peewee.TextField(null=True)
    duration_ms = peewee.IntegerField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rule_execution_logs"
        indexes = (
            (("rule",), False),
            (("created_at",), False),
        )


class ImportJob(BaseModel):
    """Tracks a bulk import operation."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="import_jobs", on_delete="CASCADE")
    source_format = peewee.TextField()
    file_name = peewee.TextField(null=True)
    status = peewee.TextField(default="pending")
    total_items = peewee.IntegerField(default=0)
    processed_items = peewee.IntegerField(default=0)
    created_items = peewee.IntegerField(default=0)
    skipped_items = peewee.IntegerField(default=0)
    failed_items = peewee.IntegerField(default=0)
    errors_json = JSONField(default=list)
    options_json = JSONField(default=dict)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "import_jobs"
        indexes = (
            (("user",), False),
            (("status",), False),
        )


class UserBackup(BaseModel):
    """Per-user backup archive."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="backups", on_delete="CASCADE")
    type = peewee.TextField(default="manual")
    status = peewee.TextField(default="pending")
    file_path = peewee.TextField(null=True)
    file_size_bytes = peewee.IntegerField(null=True)
    items_count = peewee.IntegerField(null=True)
    error = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_backups"
        indexes = (
            (("user",), False),
            (("status",), False),
        )
