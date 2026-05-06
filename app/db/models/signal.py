"""Generic signal-source SQLAlchemy models."""

from __future__ import annotations

import datetime as dt  # noqa: TC003
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONB, JSONValue, _utcnow


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_kind_external_id", "kind", "external_id", unique=True),
        Index("ix_sources_kind_is_active", "kind", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fetch_error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_fetched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    legacy_rss_feed_id: Mapped[int | None] = mapped_column(ForeignKey("rss_feeds.id", ondelete="SET NULL"), unique=True, nullable=True)
    legacy_channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), unique=True, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    legacy_rss_feed: Mapped[Any | None] = relationship("RSSFeed", back_populates="signal_sources")
    legacy_channel: Mapped[Any | None] = relationship("Channel", back_populates="signal_sources")
    subscriptions: Mapped[list[Any]] = relationship("Subscription", back_populates="source", cascade="all, delete-orphan")
    feed_items: Mapped[list[Any]] = relationship("FeedItem", back_populates="source", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_id_source_id", "user_id", "source_id", unique=True),
        Index("ix_subscriptions_user_id_is_active", "user_id", "is_active"),
        Index("ix_subscriptions_next_fetch_at", "next_fetch_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cadence_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_fetch_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    topic_constraints_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    legacy_rss_subscription_id: Mapped[int | None] = mapped_column(ForeignKey("rss_feed_subscriptions.id", ondelete="SET NULL"), unique=True, nullable=True)
    legacy_channel_subscription: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User", back_populates="subscriptions")
    source: Mapped[Source] = relationship(back_populates="subscriptions")
    legacy_rss_subscription: Mapped[Any | None] = relationship("RSSFeedSubscription", back_populates="signal_subscriptions")


class FeedItem(Base):
    __tablename__ = "feed_items"
    __table_args__ = (
        Index("ix_feed_items_source_id_external_id", "source_id", "external_id", unique=True),
        Index("ix_feed_items_published_at", "published_at"),
        Index("ix_feed_items_canonical_url", "canonical_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forwards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    legacy_rss_item_id: Mapped[int | None] = mapped_column(ForeignKey("rss_feed_items.id", ondelete="SET NULL"), unique=True, nullable=True)
    legacy_channel_post_id: Mapped[int | None] = mapped_column(ForeignKey("channel_posts.id", ondelete="SET NULL"), unique=True, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    source: Mapped[Source] = relationship(back_populates="feed_items")
    legacy_rss_item: Mapped[Any | None] = relationship("RSSFeedItem", back_populates="signal_feed_items")
    legacy_channel_post: Mapped[Any | None] = relationship("ChannelPost", back_populates="signal_feed_items")
    user_signals: Mapped[list[Any]] = relationship("UserSignal", back_populates="feed_item", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index("ix_topics_user_id_name", "user_id", "name", unique=True),
        Index("ix_topics_user_id_is_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    embedding_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User", back_populates="signal_topics")
    signals: Mapped[list[Any]] = relationship("UserSignal", back_populates="topic")


class UserSignal(Base):
    __tablename__ = "user_signals"
    __table_args__ = (
        Index("ix_user_signals_user_id_feed_item_id", "user_id", "feed_item_id", unique=True),
        Index("ix_user_signals_user_id_status", "user_id", "status"),
        Index("ix_user_signals_final_score", "final_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="candidate", nullable=False)
    heuristic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    filter_stage: Mapped[str] = mapped_column(Text, default="heuristic", nullable=False)
    evidence_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    llm_judge_json: Mapped[JSONValue] = mapped_column(JSONB, nullable=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User", back_populates="user_signals")
    feed_item: Mapped[FeedItem] = relationship(back_populates="user_signals")
    topic: Mapped[Topic | None] = relationship(back_populates="signals")


SIGNAL_MODELS = (Source, Subscription, FeedItem, Topic, UserSignal)
