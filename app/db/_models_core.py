"""Core request, summary, and user-adjacent models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import FTS5Model, JSONField, SearchField

from app.db._models_base import (
    TOPIC_SEARCH_INDEX_OPTIONS,
    BaseModel,
    _next_server_version,
    _utcnow,
    database_proxy,
)


class User(BaseModel):
    telegram_user_id = peewee.BigIntegerField(primary_key=True)
    username = peewee.TextField(null=True)
    is_owner = peewee.BooleanField(default=False)
    preferences_json = JSONField(null=True)
    linked_telegram_user_id = peewee.BigIntegerField(null=True)
    linked_telegram_username = peewee.TextField(null=True)
    linked_telegram_photo_url = peewee.TextField(null=True)
    linked_telegram_first_name = peewee.TextField(null=True)
    linked_telegram_last_name = peewee.TextField(null=True)
    linked_at = peewee.DateTimeField(null=True)
    link_nonce = peewee.TextField(null=True)
    link_nonce_expires_at = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "users"
        indexes = ((("linked_telegram_user_id",), False),)


class ClientSecret(BaseModel):
    """Client-bound secret keys for alternate authentication."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="client_secrets", on_delete="CASCADE")
    client_id = peewee.TextField()
    secret_hash = peewee.TextField()
    secret_salt = peewee.TextField()
    status = peewee.TextField(default="active")
    label = peewee.TextField(null=True)
    description = peewee.TextField(null=True)
    expires_at = peewee.DateTimeField(null=True)
    last_used_at = peewee.DateTimeField(null=True)
    failed_attempts = peewee.IntegerField(default=0)
    locked_until = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "client_secrets"
        indexes = (
            (("user", "client_id"), False),
            (("status",), False),
        )


class Chat(BaseModel):
    chat_id = peewee.BigIntegerField(primary_key=True)
    type = peewee.TextField()
    title = peewee.TextField(null=True)
    username = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "chats"


class Request(BaseModel):
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)
    type = peewee.TextField()
    status = peewee.TextField(default="pending")
    correlation_id = peewee.TextField(null=True)
    chat_id = peewee.BigIntegerField(null=True)
    user_id = peewee.BigIntegerField(null=True)
    input_url = peewee.TextField(null=True)
    normalized_url = peewee.TextField(null=True)
    dedupe_hash = peewee.TextField(null=True, unique=True)
    input_message_id = peewee.IntegerField(null=True)
    bot_reply_message_id = peewee.IntegerField(null=True)
    fwd_from_chat_id = peewee.BigIntegerField(null=True)
    fwd_from_msg_id = peewee.IntegerField(null=True)
    lang_detected = peewee.TextField(null=True)
    content_text = peewee.TextField(null=True)
    route_version = peewee.IntegerField(default=1)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    error_type = peewee.TextField(null=True)
    error_message = peewee.TextField(null=True)
    error_timestamp = peewee.DateTimeField(null=True)
    processing_time_ms = peewee.IntegerField(null=True)
    error_context_json = JSONField(null=True)

    class Meta:
        table_name = "requests"
        indexes = (
            (("user_id",), False),
            (("status",), False),
            (("created_at",), False),
            (("user_id", "created_at"), False),
        )


class TelegramMessage(BaseModel):
    request = peewee.ForeignKeyField(
        Request,
        backref="telegram_message",
        unique=True,
        on_delete="CASCADE",
    )
    message_id = peewee.IntegerField(null=True)
    chat_id = peewee.BigIntegerField(null=True)
    date_ts = peewee.IntegerField(null=True)
    text_full = peewee.TextField(null=True)
    entities_json = JSONField(null=True)
    media_type = peewee.TextField(null=True)
    media_file_ids_json = JSONField(null=True)
    forward_from_chat_id = peewee.BigIntegerField(null=True)
    forward_from_chat_type = peewee.TextField(null=True)
    forward_from_chat_title = peewee.TextField(null=True)
    forward_from_message_id = peewee.IntegerField(null=True)
    forward_date_ts = peewee.IntegerField(null=True)
    telegram_raw_json = JSONField(null=True)

    class Meta:
        table_name = "telegram_messages"


class CrawlResult(BaseModel):
    request = peewee.ForeignKeyField(
        Request,
        backref="crawl_result",
        unique=True,
        on_delete="CASCADE",
    )
    updated_at = peewee.DateTimeField(default=_utcnow)
    source_url = peewee.TextField(null=True)
    endpoint = peewee.TextField(null=True)
    http_status = peewee.IntegerField(null=True)
    status = peewee.TextField(null=True)
    options_json = JSONField(null=True)
    correlation_id = peewee.TextField(null=True)
    content_markdown = peewee.TextField(null=True)
    content_html = peewee.TextField(null=True)
    structured_json = JSONField(null=True)
    metadata_json = JSONField(null=True)
    links_json = JSONField(null=True)
    screenshots_paths_json = JSONField(null=True)
    firecrawl_success = peewee.BooleanField(null=True)
    firecrawl_error_code = peewee.TextField(null=True)
    firecrawl_error_message = peewee.TextField(null=True)
    firecrawl_details_json = JSONField(null=True)
    raw_response_json = JSONField(null=True)
    latency_ms = peewee.IntegerField(null=True)
    error_text = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "crawl_results"


class LLMCall(BaseModel):
    request = peewee.ForeignKeyField(
        Request,
        backref="llm_calls",
        null=False,
        on_delete="CASCADE",
    )
    updated_at = peewee.DateTimeField(default=_utcnow)
    provider = peewee.TextField(null=True)
    model = peewee.TextField(null=True)
    endpoint = peewee.TextField(null=True)
    request_headers_json = JSONField(null=True)
    request_messages_json = JSONField(null=True)
    response_text = peewee.TextField(null=True)
    response_json = JSONField(null=True)
    openrouter_response_text = peewee.TextField(null=True)
    openrouter_response_json = JSONField(null=True)
    tokens_prompt = peewee.IntegerField(null=True)
    tokens_completion = peewee.IntegerField(null=True)
    cost_usd = peewee.FloatField(null=True)
    latency_ms = peewee.IntegerField(null=True)
    status = peewee.TextField(null=True)
    error_text = peewee.TextField(null=True)
    structured_output_used = peewee.BooleanField(null=True)
    structured_output_mode = peewee.TextField(null=True)
    error_context_json = JSONField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "llm_calls"


class Summary(BaseModel):
    request = peewee.ForeignKeyField(Request, backref="summary", unique=True, on_delete="CASCADE")
    lang = peewee.TextField(null=True)
    json_payload = JSONField(null=True)
    insights_json = JSONField(null=True)
    version = peewee.IntegerField(default=1)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_read = peewee.BooleanField(default=False)
    is_favorited = peewee.BooleanField(default=False)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    reading_progress = peewee.FloatField(default=0.0, null=True)
    last_read_offset = peewee.IntegerField(default=0, null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summaries"
        indexes = (
            (("is_read",), False),
            (("lang",), False),
            (("created_at",), False),
        )


class TopicSearchIndex(FTS5Model):
    """FTS-backed search index for locally stored summaries."""

    request_id = SearchField()
    url = SearchField()
    title = SearchField()
    snippet = SearchField()
    source = SearchField()
    published_at = SearchField()
    body = SearchField()
    tags = SearchField()

    class Meta:
        table_name = "topic_search_index"
        database = database_proxy
        options = TOPIC_SEARCH_INDEX_OPTIONS


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
        Request,
        backref="interactions",
        null=True,
        on_delete="SET NULL",
    )
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_interactions"
        indexes = ((("user_id",), False), (("request",), False))


class AuditLog(BaseModel):
    ts = peewee.DateTimeField(default=_utcnow)
    level = peewee.TextField()
    event = peewee.TextField()
    details_json = JSONField(null=True)

    class Meta:
        table_name = "audit_logs"


class SummaryEmbedding(BaseModel):
    """Vector embeddings for semantic search."""

    summary = peewee.ForeignKeyField(Summary, backref="embedding", unique=True, on_delete="CASCADE")
    model_name = peewee.TextField()
    model_version = peewee.TextField()
    embedding_blob = peewee.BlobField()
    dimensions = peewee.IntegerField()
    language = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_embeddings"
        indexes = ((("model_name", "model_version"), False),)


class VideoDownload(BaseModel):
    """YouTube video downloads with transcripts and metadata."""

    request = peewee.ForeignKeyField(
        Request,
        backref="video_download",
        unique=True,
        on_delete="CASCADE",
    )
    video_id = peewee.TextField()
    video_file_path = peewee.TextField(null=True)
    subtitle_file_path = peewee.TextField(null=True)
    metadata_file_path = peewee.TextField(null=True)
    thumbnail_file_path = peewee.TextField(null=True)
    title = peewee.TextField(null=True)
    channel = peewee.TextField(null=True)
    channel_id = peewee.TextField(null=True)
    duration_sec = peewee.IntegerField(null=True)
    upload_date = peewee.TextField(null=True)
    view_count = peewee.BigIntegerField(null=True)
    like_count = peewee.BigIntegerField(null=True)
    resolution = peewee.TextField(null=True)
    file_size_bytes = peewee.BigIntegerField(null=True)
    video_codec = peewee.TextField(null=True)
    audio_codec = peewee.TextField(null=True)
    format_id = peewee.TextField(null=True)
    subtitle_language = peewee.TextField(null=True)
    auto_generated = peewee.BooleanField(null=True)
    transcript_text = peewee.TextField(null=True)
    transcript_source = peewee.TextField(null=True)
    download_started_at = peewee.DateTimeField(null=True)
    download_completed_at = peewee.DateTimeField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)
    status = peewee.TextField(default="pending")
    error_text = peewee.TextField(null=True)

    class Meta:
        table_name = "video_downloads"
        indexes = (
            (("video_id",), False),
            (("status",), False),
            (("created_at",), False),
        )


class AudioGeneration(BaseModel):
    """Cached TTS audio files generated from summaries."""

    summary = peewee.ForeignKeyField(
        Summary,
        backref="audio_generations",
        unique=True,
        on_delete="CASCADE",
    )
    provider = peewee.TextField(default="elevenlabs")
    voice_id = peewee.TextField()
    model = peewee.TextField()
    file_path = peewee.TextField(null=True)
    file_size_bytes = peewee.BigIntegerField(null=True)
    duration_sec = peewee.FloatField(null=True)
    char_count = peewee.IntegerField(null=True)
    source_field = peewee.TextField(default="summary_1000")
    language = peewee.TextField(null=True)
    status = peewee.TextField(default="pending")
    error_text = peewee.TextField(null=True)
    latency_ms = peewee.IntegerField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "audio_generations"
        indexes = (
            (("status",), False),
            (("created_at",), False),
        )


class AttachmentProcessing(BaseModel):
    """Tracks image and PDF attachment processing."""

    id = peewee.AutoField()
    request = peewee.ForeignKeyField(
        Request,
        backref="attachment",
        unique=True,
        on_delete="CASCADE",
    )
    file_type = peewee.TextField()
    mime_type = peewee.TextField(null=True)
    file_name = peewee.TextField(null=True)
    file_size_bytes = peewee.BigIntegerField(null=True)
    page_count = peewee.IntegerField(null=True)
    extracted_text_length = peewee.IntegerField(null=True)
    vision_used = peewee.BooleanField(default=False)
    vision_pages_count = peewee.IntegerField(null=True)
    processing_method = peewee.TextField(null=True)
    status = peewee.TextField(default="pending")
    error_text = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "attachment_processing"
        indexes = (
            (("status",), False),
            (("created_at",), False),
        )


class UserDevice(BaseModel):
    """Mobile devices registered for push notifications."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="devices", on_delete="CASCADE")
    token = peewee.TextField(unique=True)
    platform = peewee.TextField()
    device_id = peewee.TextField(null=True)
    is_active = peewee.BooleanField(default=True)
    last_seen_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_devices"
        indexes = (
            (("user", "platform"), False),
            (("token",), True),
        )


class RefreshToken(BaseModel):
    """Store for refresh tokens to support revocation and session management."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="refresh_tokens", on_delete="CASCADE")
    token_hash = peewee.TextField(index=True)
    client_id = peewee.TextField(null=True)
    device_info = peewee.TextField(null=True)
    ip_address = peewee.TextField(null=True)
    is_revoked = peewee.BooleanField(default=False)
    expires_at = peewee.DateTimeField()
    last_used_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "refresh_tokens"
        indexes = ((("user", "client_id"), False),)
