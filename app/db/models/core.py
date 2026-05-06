"""Core SQLAlchemy models for users, requests, summaries, and media records."""

from __future__ import annotations

import datetime as dt  # noqa: TC003 - SQLAlchemy resolves string annotations at runtime.

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONB, JSONValue, _next_server_version, _utcnow


def _json_column() -> Mapped[JSONValue]:
    return mapped_column(JSONB, nullable=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_linked_telegram_user_id", "linked_telegram_user_id"),)

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferences_json: Mapped[JSONValue] = _json_column()
    linked_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    linked_telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_telegram_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_telegram_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_telegram_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    link_nonce: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_nonce_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    client_secrets: Mapped[list[ClientSecret]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    devices: Mapped[list[UserDevice]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ClientSecret(Base):
    __tablename__ = "client_secrets"
    __table_args__ = (
        Index("ix_client_secrets_user_id_client_id", "user_id", "client_id"),
        Index("ix_client_secrets_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    secret_salt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="client_secrets")


class Chat(Base):
    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_user_id", "user_id"),
        Index("ix_requests_status", "status"),
        Index("ix_requests_created_at", "created_at"),
        Index("ix_requests_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_hash: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    input_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bot_reply_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fwd_from_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fwd_from_msg_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lang_detected: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_timestamp: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_context_json: Mapped[JSONValue] = _json_column()

    telegram_message: Mapped[TelegramMessage | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    crawl_result: Mapped[CrawlResult | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list[LLMCall]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    summary: Mapped[Summary | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    interactions: Mapped[list[UserInteraction]] = relationship(back_populates="request")
    video_download: Mapped[VideoDownload | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    attachment: Mapped[AttachmentProcessing | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    date_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities_json: Mapped[JSONValue] = _json_column()
    media_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_file_ids_json: Mapped[JSONValue] = _json_column()
    forward_from_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forward_from_chat_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    forward_from_chat_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    forward_from_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forward_date_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_raw_json: Mapped[JSONValue] = _json_column()

    request: Mapped[Request] = relationship(back_populates="telegram_message")


class CrawlResult(Base):
    __tablename__ = "crawl_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    options_json: Mapped[JSONValue] = _json_column()
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[JSONValue] = _json_column()
    metadata_json: Mapped[JSONValue] = _json_column()
    links_json: Mapped[JSONValue] = _json_column()
    screenshots_paths_json: Mapped[JSONValue] = _json_column()
    firecrawl_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    firecrawl_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    firecrawl_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    firecrawl_details_json: Mapped[JSONValue] = _json_column()
    raw_response_json: Mapped[JSONValue] = _json_column()
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    request: Mapped[Request] = relationship(back_populates="crawl_result")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_headers_json: Mapped[JSONValue] = _json_column()
    request_messages_json: Mapped[JSONValue] = _json_column()
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[JSONValue] = _json_column()
    openrouter_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_response_json: Mapped[JSONValue] = _json_column()
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_completion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_output_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    structured_output_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_context_json: Mapped[JSONValue] = _json_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    request: Mapped[Request] = relationship(back_populates="llm_calls")


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (
        Index("ix_summaries_is_read", "is_read"),
        Index("ix_summaries_lang", "lang"),
        Index("ix_summaries_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    lang: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_payload: Mapped[JSONValue] = _json_column()
    insights_json: Mapped[JSONValue] = _json_column()
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    server_version: Mapped[int] = mapped_column(
        BigInteger, default=_next_server_version, nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reading_progress: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)
    last_read_offset: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    request: Mapped[Request] = relationship(back_populates="summary")
    embedding: Mapped[SummaryEmbedding | None] = relationship(
        back_populates="summary", cascade="all, delete-orphan"
    )
    audio_generations: Mapped[list[AudioGeneration]] = relationship(
        back_populates="summary", cascade="all, delete-orphan"
    )


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (
        Index("ix_user_interactions_user_id", "user_id"),
        Index("ix_user_interactions_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    forward_from_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forward_from_chat_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    forward_from_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_output_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    request: Mapped[Request | None] = relationship(back_populates="interactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[JSONValue] = _json_column()


class SummaryEmbedding(Base):
    __tablename__ = "summary_embeddings"
    __table_args__ = (Index("ix_summary_embeddings_model_name_model_version", "model_name", "model_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("summaries.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    summary: Mapped[Summary] = relationship(back_populates="embedding")


class VideoDownload(Base):
    __tablename__ = "video_downloads"
    __table_args__ = (
        Index("ix_video_downloads_video_id", "video_id"),
        Index("ix_video_downloads_status", "status"),
        Index("ix_video_downloads_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    video_id: Mapped[str] = mapped_column(Text, nullable=False)
    video_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_generated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    download_completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[Request] = relationship(back_populates="video_download")


class AudioGeneration(Base):
    __tablename__ = "audio_generations"
    __table_args__ = (
        Index("ix_audio_generations_status", "status"),
        Index("ix_audio_generations_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("summaries.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, default="elevenlabs", nullable=False)
    voice_id: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_field: Mapped[str] = mapped_column(Text, default="summary_1000", nullable=False)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    summary: Mapped[Summary] = relationship(back_populates="audio_generations")


class AttachmentProcessing(Base):
    __tablename__ = "attachment_processing"
    __table_args__ = (
        Index("ix_attachment_processing_status", "status"),
        Index("ix_attachment_processing_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vision_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vision_pages_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    request: Mapped[Request] = relationship(back_populates="attachment")


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        Index("ix_user_devices_user_id_platform", "user_id", "platform"),
        Index("ix_user_devices_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="devices")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id_client_id", "user_id", "client_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


CORE_MODELS: tuple[type[Base], ...] = (
    User,
    ClientSecret,
    Chat,
    Request,
    TelegramMessage,
    CrawlResult,
    LLMCall,
    Summary,
    UserInteraction,
    AuditLog,
    SummaryEmbedding,
    VideoDownload,
    AudioGeneration,
    AttachmentProcessing,
    UserDevice,
    RefreshToken,
)

__all__ = [
    "CORE_MODELS",
    "AttachmentProcessing",
    "AudioGeneration",
    "AuditLog",
    "Chat",
    "ClientSecret",
    "CrawlResult",
    "LLMCall",
    "RefreshToken",
    "Request",
    "Summary",
    "SummaryEmbedding",
    "TelegramMessage",
    "User",
    "UserDevice",
    "UserInteraction",
    "VideoDownload",
]
