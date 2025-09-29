"""Peewee ORM models for the application database."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import peewee

# A proxy that will be initialised with the concrete database instance at runtime.
database_proxy: peewee.Database = peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    """Base Peewee model bound to the lazily initialised database proxy."""

    class Meta:
        database = database_proxy
        legacy_table_names = False


class User(BaseModel):
    telegram_user_id = peewee.BigIntegerField(primary_key=True)
    username = peewee.TextField(null=True)
    is_owner = peewee.BooleanField(default=False)
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)

    class Meta:
        table_name = "users"


class Chat(BaseModel):
    chat_id = peewee.BigIntegerField(primary_key=True)
    type = peewee.TextField()
    title = peewee.TextField(null=True)
    username = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)

    class Meta:
        table_name = "chats"


class Request(BaseModel):
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)
    type = peewee.TextField()
    status = peewee.TextField(default="pending")
    correlation_id = peewee.TextField(null=True)
    chat_id = peewee.BigIntegerField(null=True)
    user_id = peewee.BigIntegerField(null=True)
    input_url = peewee.TextField(null=True)
    normalized_url = peewee.TextField(null=True)
    dedupe_hash = peewee.TextField(null=True, unique=True)
    input_message_id = peewee.IntegerField(null=True)
    fwd_from_chat_id = peewee.BigIntegerField(null=True)
    fwd_from_msg_id = peewee.IntegerField(null=True)
    lang_detected = peewee.TextField(null=True)
    content_text = peewee.TextField(null=True)
    route_version = peewee.IntegerField(default=1)

    class Meta:
        table_name = "requests"


class TelegramMessage(BaseModel):
    request = peewee.ForeignKeyField(
        Request, backref="telegram_message", unique=True, on_delete="CASCADE"
    )
    message_id = peewee.IntegerField(null=True)
    chat_id = peewee.BigIntegerField(null=True)
    date_ts = peewee.IntegerField(null=True)
    text_full = peewee.TextField(null=True)
    entities_json = peewee.TextField(null=True)
    media_type = peewee.TextField(null=True)
    media_file_ids_json = peewee.TextField(null=True)
    forward_from_chat_id = peewee.BigIntegerField(null=True)
    forward_from_chat_type = peewee.TextField(null=True)
    forward_from_chat_title = peewee.TextField(null=True)
    forward_from_message_id = peewee.IntegerField(null=True)
    forward_date_ts = peewee.IntegerField(null=True)
    telegram_raw_json = peewee.TextField(null=True)

    class Meta:
        table_name = "telegram_messages"


class CrawlResult(BaseModel):
    request = peewee.ForeignKeyField(
        Request, backref="crawl_result", unique=True, on_delete="CASCADE"
    )
    source_url = peewee.TextField(null=True)
    endpoint = peewee.TextField(null=True)
    http_status = peewee.IntegerField(null=True)
    status = peewee.TextField(null=True)
    options_json = peewee.TextField(null=True)
    correlation_id = peewee.TextField(null=True)
    content_markdown = peewee.TextField(null=True)
    content_html = peewee.TextField(null=True)
    structured_json = peewee.TextField(null=True)
    metadata_json = peewee.TextField(null=True)
    links_json = peewee.TextField(null=True)
    screenshots_paths_json = peewee.TextField(null=True)
    firecrawl_success = peewee.BooleanField(null=True)
    firecrawl_error_code = peewee.TextField(null=True)
    firecrawl_error_message = peewee.TextField(null=True)
    firecrawl_details_json = peewee.TextField(null=True)
    raw_response_json = peewee.TextField(null=True)
    latency_ms = peewee.IntegerField(null=True)
    error_text = peewee.TextField(null=True)

    class Meta:
        table_name = "crawl_results"


class LLMCall(BaseModel):
    request = peewee.ForeignKeyField(Request, backref="llm_calls", null=True, on_delete="SET NULL")
    provider = peewee.TextField(null=True)
    model = peewee.TextField(null=True)
    endpoint = peewee.TextField(null=True)
    request_headers_json = peewee.TextField(null=True)
    request_messages_json = peewee.TextField(null=True)
    response_text = peewee.TextField(null=True)
    response_json = peewee.TextField(null=True)
    openrouter_response_text = peewee.TextField(null=True)
    openrouter_response_json = peewee.TextField(null=True)
    tokens_prompt = peewee.IntegerField(null=True)
    tokens_completion = peewee.IntegerField(null=True)
    cost_usd = peewee.FloatField(null=True)
    latency_ms = peewee.IntegerField(null=True)
    status = peewee.TextField(null=True)
    error_text = peewee.TextField(null=True)
    structured_output_used = peewee.BooleanField(null=True)
    structured_output_mode = peewee.TextField(null=True)
    error_context_json = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)

    class Meta:
        table_name = "llm_calls"


class Summary(BaseModel):
    request = peewee.ForeignKeyField(Request, backref="summary", unique=True, on_delete="CASCADE")
    lang = peewee.TextField(null=True)
    json_payload = peewee.TextField(null=True)
    insights_json = peewee.TextField(null=True)
    version = peewee.IntegerField(default=1)
    is_read = peewee.BooleanField(default=False)
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)

    class Meta:
        table_name = "summaries"


class UserInteraction(BaseModel):
    user_id = peewee.BigIntegerField()
    chat_id = peewee.BigIntegerField(null=True)
    message_id = peewee.IntegerField(null=True)
    interaction_type = peewee.TextField()
    command = peewee.TextField(null=True)
    input_text = peewee.TextField(null=True)
    input_url = peewee.TextField(null=True)
    has_forward = peewee.BooleanField(default=False)
    forward_from_chat_id = peewee.BigIntegerField(null=True)
    forward_from_chat_title = peewee.TextField(null=True)
    forward_from_message_id = peewee.IntegerField(null=True)
    media_type = peewee.TextField(null=True)
    correlation_id = peewee.TextField(null=True)
    structured_output_enabled = peewee.BooleanField(default=False)
    response_sent = peewee.BooleanField(default=False)
    response_type = peewee.TextField(null=True)
    error_occurred = peewee.BooleanField(default=False)
    error_message = peewee.TextField(null=True)
    processing_time_ms = peewee.IntegerField(null=True)
    request = peewee.ForeignKeyField(
        Request, backref="interactions", null=True, on_delete="SET NULL"
    )
    created_at = peewee.DateTimeField(default=_dt.datetime.utcnow)
    updated_at = peewee.DateTimeField(default=_dt.datetime.utcnow)

    class Meta:
        table_name = "user_interactions"
        indexes = ((("user_id",), False), (("request",), False))


class AuditLog(BaseModel):
    ts = peewee.DateTimeField(default=_dt.datetime.utcnow)
    level = peewee.TextField()
    event = peewee.TextField()
    details_json = peewee.TextField(null=True)

    class Meta:
        table_name = "audit_logs"


ALL_MODELS: tuple[type[BaseModel], ...] = (
    User,
    Chat,
    Request,
    TelegramMessage,
    CrawlResult,
    LLMCall,
    Summary,
    UserInteraction,
    AuditLog,
)


def model_to_dict(model: BaseModel | None) -> dict[str, Any] | None:
    """Convert a Peewee model instance to a plain dictionary."""

    if model is None:
        return None
    data: dict[str, Any] = {}
    for field_name in model._meta.sorted_field_names:
        value = getattr(model, field_name)
        if isinstance(value, peewee.Model):
            value = value.get_id()
        data[field_name] = value
    return data
