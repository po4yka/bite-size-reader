"""SQLite implementation of RSS feed repository.

This adapter handles persistence for RSS feeds, subscriptions, and feed items.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import (
    ChannelCategory,
    RSSFeed,
    RSSFeedItem,
    RSSFeedSubscription,
    model_to_dict,
)
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

logger = get_logger(__name__)


class SqliteRSSFeedRepositoryAdapter(SqliteBaseRepository):
    """Adapter for RSS feed, subscription, and feed item operations."""

    # --- Feed CRUD ---

    async def async_get_or_create_feed(self, url: str) -> dict[str, Any]:
        """Find a feed by URL or create a new one."""

        def _query() -> dict[str, Any]:
            feed, _created = RSSFeed.get_or_create(url=url)
            d = model_to_dict(feed)
            assert d is not None
            return d

        return await self._execute(_query, operation_name="get_or_create_feed")

    async def async_get_feed(self, feed_id: int) -> dict[str, Any] | None:
        """Return a feed by ID."""

        def _query() -> dict[str, Any] | None:
            try:
                feed = RSSFeed.get_by_id(feed_id)
            except RSSFeed.DoesNotExist:
                return None
            return model_to_dict(feed)

        return await self._execute(_query, operation_name="get_feed", read_only=True)

    async def async_update_feed(self, feed_id: int, **fields: Any) -> None:
        """Update feed fields by ID."""

        def _update() -> None:
            update_data = {getattr(RSSFeed, k): v for k, v in fields.items() if hasattr(RSSFeed, k)}
            if update_data:
                update_data[RSSFeed.updated_at] = datetime.now(UTC)
                RSSFeed.update(update_data).where(RSSFeed.id == feed_id).execute()

        await self._execute(_update, operation_name="update_feed")

    async def async_list_active_feeds(self) -> list[dict[str, Any]]:
        """Return feeds that have at least one active subscription."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                RSSFeed.select()
                .join(RSSFeedSubscription)
                .where(
                    (RSSFeed.is_active == True)  # noqa: E712
                    & (RSSFeedSubscription.is_active == True)  # noqa: E712
                )
                .distinct()
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="list_active_feeds", read_only=True)

    # --- Subscription CRUD ---

    async def async_create_subscription(
        self,
        user_id: int,
        feed_id: int,
        category_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a subscription for a user to a feed."""

        def _insert() -> dict[str, Any]:
            try:
                sub = RSSFeedSubscription.create(
                    user=user_id,
                    feed=feed_id,
                    category=category_id,
                )
            except peewee.IntegrityError:
                # Already subscribed -- return existing
                sub = RSSFeedSubscription.get(
                    (RSSFeedSubscription.user == user_id) & (RSSFeedSubscription.feed == feed_id)
                )
            d = model_to_dict(sub)
            assert d is not None
            return d

        return await self._execute(_insert, operation_name="create_subscription")

    async def async_delete_subscription(self, subscription_id: int) -> None:
        """Delete a subscription by ID."""

        def _delete() -> None:
            RSSFeedSubscription.delete().where(RSSFeedSubscription.id == subscription_id).execute()

        await self._execute(_delete, operation_name="delete_subscription")

    async def async_list_user_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        """Return all subscriptions for a user, joined with feed details."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                RSSFeedSubscription.select(RSSFeedSubscription, RSSFeed, ChannelCategory)
                .join(RSSFeed, on=(RSSFeedSubscription.feed == RSSFeed.id))
                .switch(RSSFeedSubscription)
                .join(
                    ChannelCategory,
                    peewee.JOIN.LEFT_OUTER,
                    on=(RSSFeedSubscription.category == ChannelCategory.id),
                )
                .where(RSSFeedSubscription.user == user_id)
                .order_by(RSSFeedSubscription.created_at.desc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    feed = model_to_dict(row.feed)
                    if feed is not None:
                        d["feed_title"] = feed.get("title")
                        d["feed_url"] = feed.get("url")
                        d["site_url"] = feed.get("site_url")
                        d["feed_description"] = feed.get("description")
                    cat = row.category
                    if cat and cat.id:
                        d["category_name"] = cat.name
                    else:
                        d["category_name"] = None
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="list_user_subscriptions", read_only=True)

    # --- Feed items ---

    async def async_create_feed_item(
        self,
        feed_id: int,
        guid: str,
        title: str | None,
        url: str | None,
        content: str | None,
        author: str | None,
        published_at: datetime | None,
    ) -> dict[str, Any] | None:
        """Insert a feed item, ignoring duplicates (by feed+guid)."""

        def _insert() -> dict[str, Any] | None:
            try:
                item = RSSFeedItem.create(
                    feed=feed_id,
                    guid=guid,
                    title=title,
                    url=url,
                    content=content,
                    author=author,
                    published_at=published_at,
                )
                return model_to_dict(item)
            except peewee.IntegrityError:
                return None

        return await self._execute(_insert, operation_name="create_feed_item")

    async def async_list_feed_items(
        self,
        feed_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return paginated feed items for a feed."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                RSSFeedItem.select()
                .where(RSSFeedItem.feed == feed_id)
                .order_by(RSSFeedItem.published_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="list_feed_items", read_only=True)
