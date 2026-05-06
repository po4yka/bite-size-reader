"""Batch processing SQLAlchemy models."""

from __future__ import annotations

import datetime as dt  # noqa: TC003 - SQLAlchemy resolves string annotations at runtime.
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONB, JSONValue, _next_server_version, _utcnow


class BatchSession(Base):
    __tablename__ = "batch_sessions"
    __table_args__ = (
        Index("ix_batch_sessions_user_id", "user_id"),
        Index("ix_batch_sessions_status", "status"),
        Index("ix_batch_sessions_created_at", "created_at"),
        Index("ix_batch_sessions_relationship_type", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    total_urls: Mapped[int] = mapped_column(Integer, nullable=False)
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    relationship_metadata_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    combined_summary_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="processing", nullable=False)
    analysis_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=_next_server_version, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User", back_populates="batch_sessions")
    items: Mapped[list[Any]] = relationship("BatchSessionItem", back_populates="batch_session", cascade="all, delete-orphan")


class BatchSessionItem(Base):
    __tablename__ = "batch_session_items"
    __table_args__ = (
        Index("ix_batch_session_items_session_position", "batch_session_id", "position"),
        Index("ix_batch_session_items_session_request", "batch_session_id", "request_id", unique=True),
        Index("ix_batch_session_items_is_series_part", "is_series_part"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_session_id: Mapped[int] = mapped_column(ForeignKey("batch_sessions.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_series_part: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    series_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    batch_session: Mapped[BatchSession] = relationship(back_populates="items")
    request: Mapped[Any] = relationship("Request", back_populates="batch_item")


BATCH_MODELS = (BatchSession, BatchSessionItem)
