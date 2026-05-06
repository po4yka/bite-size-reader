"""Aggregation session SQLAlchemy models."""

from __future__ import annotations

import datetime as dt  # noqa: TC003 - SQLAlchemy resolves string annotations at runtime.

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONB, JSONValue, _next_server_version, _utcnow


def _json() -> Mapped[JSONValue]:
    return mapped_column(JSONB, nullable=True)


class AggregationSession(Base):
    __tablename__ = "aggregation_sessions"
    __table_args__ = (
        Index("ix_aggregation_sessions_user_id", "user_id"),
        Index("ix_aggregation_sessions_status", "status"),
        Index("ix_aggregation_sessions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allow_partial_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    bundle_metadata_json: Mapped[JSONValue] = _json()
    aggregation_output_json: Mapped[JSONValue] = _json()
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_details_json: Mapped[JSONValue] = _json()
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queued_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_progress_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=_next_server_version, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[object] = relationship("User", back_populates="aggregation_sessions")
    items: Mapped[list[AggregationSessionItem]] = relationship(back_populates="aggregation_session", cascade="all, delete-orphan")


class AggregationSessionItem(Base):
    __tablename__ = "aggregation_session_items"
    __table_args__ = (
        Index("ix_aggregation_session_items_session_position", "aggregation_session_id", "position", unique=True),
        Index("ix_aggregation_session_items_session_source_item", "aggregation_session_id", "source_item_id"),
        Index("ix_aggregation_session_items_request_id", "request_id"),
        Index("ix_aggregation_session_items_status", "status"),
        Index("ix_aggregation_session_items_duplicate_of_item_id", "duplicate_of_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aggregation_session_id: Mapped[int] = mapped_column(Integer, ForeignKey("aggregation_sessions.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("requests.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_media_group_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metadata_json: Mapped[JSONValue] = _json()
    normalized_document_json: Mapped[JSONValue] = _json()
    extraction_metadata_json: Mapped[JSONValue] = _json()
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    duplicate_of_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_details_json: Mapped[JSONValue] = _json()
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    aggregation_session: Mapped[AggregationSession] = relationship(back_populates="items")
    request: Mapped[object | None] = relationship("Request", back_populates="aggregation_items")


AGGREGATION_MODELS = (AggregationSession, AggregationSessionItem)
