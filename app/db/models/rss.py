"""RSS feed SQLAlchemy models."""

from __future__ import annotations

import datetime as dt  # noqa: TC003
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import _utcnow


class RSSFeed(Base):
    __tablename__ = "rss_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_fetched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    subscriptions: Mapped[list[Any]] = relationship("RSSFeedSubscription", back_populates="feed", cascade="all, delete-orphan")
    items: Mapped[list[Any]] = relationship("RSSFeedItem", back_populates="feed", cascade="all, delete-orphan")
    signal_sources: Mapped[list[Any]] = relationship("Source", back_populates="legacy_rss_feed")


class RSSFeedSubscription(Base):
    __tablename__ = "rss_feed_subscriptions"
    __table_args__ = (Index("ix_rss_feed_subscriptions_user_id_feed_id", "user_id", "feed_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    feed_id: Mapped[int] = mapped_column(ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("channel_categories.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User", back_populates="rss_subscriptions")
    feed: Mapped[RSSFeed] = relationship(back_populates="subscriptions")
    category: Mapped[Any | None] = relationship("ChannelCategory", back_populates="rss_subscriptions")
    signal_subscriptions: Mapped[list[Any]] = relationship("Subscription", back_populates="legacy_rss_subscription")


class RSSFeedItem(Base):
    __tablename__ = "rss_feed_items"
    __table_args__ = (
        Index("ix_rss_feed_items_feed_id_guid", "feed_id", "guid", unique=True),
        Index("ix_rss_feed_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False)
    guid: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    feed: Mapped[RSSFeed] = relationship(back_populates="items")
    deliveries: Mapped[list[Any]] = relationship("RSSItemDelivery", back_populates="item", cascade="all, delete-orphan")
    signal_feed_items: Mapped[list[Any]] = relationship("FeedItem", back_populates="legacy_rss_item")


class RSSItemDelivery(Base):
    __tablename__ = "rss_item_deliveries"
    __table_args__ = (Index("ix_rss_item_deliveries_user_id_item_id", "user_id", "item_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("rss_feed_items.id", ondelete="CASCADE"), nullable=False)
    summary_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[Any] = relationship("User")
    item: Mapped[RSSFeedItem] = relationship(back_populates="deliveries")


RSS_MODELS = (RSSFeed, RSSFeedSubscription, RSSFeedItem, RSSItemDelivery)
