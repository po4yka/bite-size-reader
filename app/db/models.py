"""Peewee ORM models for the application database."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import peewee
from playhouse.sqlite_ext import FTS5Model, JSONField, SearchField

from app.core.time_utils import UTC

# A proxy that will be initialised with the concrete database instance at runtime.
database_proxy: peewee.Database = peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    """Base Peewee model bound to the lazily initialised database proxy."""

    def save(self, *args: Any, **kwargs: Any) -> int:
        """Ensure updated_at/server_version fields stay monotonic on every save."""
        now = _utcnow()

        if hasattr(self, "updated_at"):
            self.updated_at = now

        if hasattr(self, "server_version"):
            current = getattr(self, "server_version", 0) or 0
            next_version = int(now.timestamp() * 1000)
            if next_version <= current:
                next_version = current + 1
            self.server_version = next_version
            if hasattr(self, "version"):
                self.version = next_version

        return super().save(*args, **kwargs)

    class Meta:
        database = database_proxy
        legacy_table_names = False


def _utcnow() -> _dt.datetime:
    """Timezone-aware UTC now (avoids deprecated datetime.utcnow)."""
    return _dt.datetime.now(UTC)


def _next_server_version() -> int:
    """Monotonic-ish server version seed based on current UTC timestamp (ms)."""
    return int(_utcnow().timestamp() * 1000)


class User(BaseModel):
    telegram_user_id = peewee.BigIntegerField(primary_key=True)
    username = peewee.TextField(null=True)
    is_owner = peewee.BooleanField(default=False)
    preferences_json = JSONField(null=True)  # User preferences (lang, notifications, app settings)
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
    status = peewee.TextField(default="active")  # active | revoked | expired | locked
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
    fwd_from_chat_id = peewee.BigIntegerField(null=True)
    fwd_from_msg_id = peewee.IntegerField(null=True)
    lang_detected = peewee.TextField(null=True)
    content_text = peewee.TextField(null=True)
    route_version = peewee.IntegerField(default=1)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "requests"
        indexes = (
            # Single column indexes
            (("user_id",), False),  # Heavily filtered in all API queries
            (("status",), False),  # Filtered in status queries
            (("created_at",), False),  # Used for sorting
            # Composite index for common query pattern (user filtering + date sorting)
            (("user_id", "created_at"), False),
        )


class TelegramMessage(BaseModel):
    request = peewee.ForeignKeyField(
        Request, backref="telegram_message", unique=True, on_delete="CASCADE"
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
        Request, backref="crawl_result", unique=True, on_delete="CASCADE"
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
        Request, backref="llm_calls", null=False, on_delete="CASCADE"
    )  # Phase 2: Made NOT NULL for data integrity
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
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summaries"
        indexes = (
            (("is_read",), False),  # Filtered in GET /summaries for unread count
            (("lang",), False),  # Filtered in GET /summaries by language
            (("created_at",), False),  # Filtered in delta sync
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
        options = {"tokenize": "unicode61 remove_diacritics 2"}


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
    language = peewee.TextField(null=True)  # Language code (en, ru, auto)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_embeddings"
        indexes = ((("model_name", "model_version"), False),)


class VideoDownload(BaseModel):
    """YouTube video downloads with transcripts and metadata."""

    request = peewee.ForeignKeyField(
        Request, backref="video_download", unique=True, on_delete="CASCADE"
    )
    video_id = peewee.TextField()  # YouTube video ID
    video_file_path = peewee.TextField(null=True)  # Path to downloaded video file
    subtitle_file_path = peewee.TextField(null=True)  # Path to subtitle file (.vtt)
    metadata_file_path = peewee.TextField(null=True)  # Path to metadata JSON file
    thumbnail_file_path = peewee.TextField(null=True)  # Path to thumbnail image

    # Video metadata
    title = peewee.TextField(null=True)
    channel = peewee.TextField(null=True)
    channel_id = peewee.TextField(null=True)
    duration_sec = peewee.IntegerField(null=True)
    upload_date = peewee.TextField(null=True)  # YYYYMMDD format
    view_count = peewee.BigIntegerField(null=True)
    like_count = peewee.BigIntegerField(null=True)

    # Download details
    resolution = peewee.TextField(null=True)  # e.g., "1080p", "720p"
    file_size_bytes = peewee.BigIntegerField(null=True)
    video_codec = peewee.TextField(null=True)  # e.g., "avc1"
    audio_codec = peewee.TextField(null=True)  # e.g., "mp4a"
    format_id = peewee.TextField(null=True)  # yt-dlp format identifier

    # Transcript details
    subtitle_language = peewee.TextField(null=True)  # Language of extracted subtitles
    auto_generated = peewee.BooleanField(null=True)  # Whether subtitles are auto-generated
    transcript_text = peewee.TextField(null=True)  # Extracted transcript (cached)
    transcript_source = peewee.TextField(null=True)  # "youtube-transcript-api" or "vtt"

    # Timestamps
    download_started_at = peewee.DateTimeField(null=True)
    download_completed_at = peewee.DateTimeField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    # Status tracking
    status = peewee.TextField(default="pending")  # 'pending', 'downloading', 'completed', 'error'
    error_text = peewee.TextField(null=True)

    class Meta:
        table_name = "video_downloads"
        indexes = (
            (("video_id",), False),
            (("status",), False),
            (("created_at",), False),
        )


class AttachmentProcessing(BaseModel):
    """Tracks image and PDF attachment processing."""

    id = peewee.AutoField()
    request = peewee.ForeignKeyField(
        Request, backref="attachment", unique=True, on_delete="CASCADE"
    )
    file_type = peewee.TextField()  # "image", "pdf"
    mime_type = peewee.TextField(null=True)
    file_name = peewee.TextField(null=True)
    file_size_bytes = peewee.BigIntegerField(null=True)
    page_count = peewee.IntegerField(null=True)
    extracted_text_length = peewee.IntegerField(null=True)
    vision_used = peewee.BooleanField(default=False)
    vision_pages_count = peewee.IntegerField(null=True)
    processing_method = peewee.TextField(null=True)  # "vision", "text_extraction", "hybrid"
    status = peewee.TextField(default="pending")  # "pending", "processing", "completed", "error"
    error_text = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "attachment_processing"
        indexes = (
            (("status",), False),
            (("created_at",), False),
        )


class Collection(BaseModel):
    """User-created collections for organizing summaries."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="collections", on_delete="CASCADE")
    name = peewee.TextField()
    description = peewee.TextField(null=True)
    parent = peewee.ForeignKeyField("self", backref="children", null=True, on_delete="SET NULL")
    position = peewee.IntegerField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)
    is_shared = peewee.BooleanField(default=False)
    share_count = peewee.IntegerField(default=0)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "collections"
        indexes = (
            (("user", "name"), True),  # Unique name per user
            (("user", "parent", "name"), False),
            (("updated_at",), False),
            (("parent", "position"), False),
        )


class UserDevice(BaseModel):
    """Mobile devices registered for push notifications."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="devices", on_delete="CASCADE")
    token = peewee.TextField(unique=True)  # FCM/APNS token
    platform = peewee.TextField()  # ios | android
    device_id = peewee.TextField(null=True)  # Unique device identifier
    is_active = peewee.BooleanField(default=True)
    last_seen_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_devices"
        indexes = (
            (("user", "platform"), False),
            (("token",), True),
        )


class CollectionItem(BaseModel):
    """Link table for items in a collection."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="items", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, backref="collection_items", on_delete="CASCADE")
    position = peewee.IntegerField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_items"
        indexes = (
            (("collection", "summary"), True),  # Prevent duplicate items
            (("collection", "position"), False),
        )


class CollectionCollaborator(BaseModel):
    """Collaborators on a collection."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="collaborators", on_delete="CASCADE")
    user = peewee.ForeignKeyField(User, backref="collection_collaborations", on_delete="CASCADE")
    role = peewee.TextField()  # owner|editor|viewer
    status = peewee.TextField(default="active")  # active|pending|revoked
    invited_by = peewee.ForeignKeyField(User, backref="collection_invites_sent", null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_collaborators"
        indexes = (
            (("collection", "user"), True),
            (("user",), False),
        )


class CollectionInvite(BaseModel):
    """Invite tokens for collection collaboration."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="invites", on_delete="CASCADE")
    token = peewee.TextField(unique=True)
    role = peewee.TextField()  # editor|viewer
    expires_at = peewee.DateTimeField(null=True)
    used_at = peewee.DateTimeField(null=True)
    invited_email = peewee.TextField(null=True)
    invited_user_id = peewee.BigIntegerField(null=True)
    status = peewee.TextField(default="active")  # active|used|revoked|expired
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_invites"
        indexes = (
            (("collection",), False),
            (("status",), False),
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


class KarakeepSync(BaseModel):
    """Track synced items between BSR and Karakeep."""

    id = peewee.AutoField()
    # FK to Summary with CASCADE delete (null if synced from Karakeep)
    bsr_summary = peewee.ForeignKeyField(
        Summary,
        backref="karakeep_syncs",
        null=True,
        on_delete="CASCADE",
    )
    karakeep_bookmark_id = peewee.TextField(null=True)  # Karakeep bookmark ID
    url_hash = peewee.TextField(index=True)  # URL hash for deduplication
    sync_direction = peewee.TextField()  # 'bsr_to_karakeep' or 'karakeep_to_bsr'
    synced_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)
    # Timestamp tracking for conflict resolution
    bsr_modified_at = peewee.DateTimeField(null=True)  # Last BSR status update
    karakeep_modified_at = peewee.DateTimeField(null=True)  # Last Karakeep status update

    class Meta:
        table_name = "karakeep_sync"
        indexes = (
            # Unique constraint prevents duplicate sync records for same URL/direction
            (("url_hash", "sync_direction"), True),
            (("synced_at",), False),
            (("bsr_summary",), False),
        )


ALL_MODELS: tuple[type[BaseModel], ...] = (
    User,
    Chat,
    Request,
    TelegramMessage,
    CrawlResult,
    LLMCall,
    Summary,
    TopicSearchIndex,
    UserInteraction,
    AuditLog,
    SummaryEmbedding,
    VideoDownload,
    AttachmentProcessing,
    ClientSecret,
    Collection,
    CollectionItem,
    CollectionCollaborator,
    CollectionInvite,
    UserDevice,
    RefreshToken,
    KarakeepSync,
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
