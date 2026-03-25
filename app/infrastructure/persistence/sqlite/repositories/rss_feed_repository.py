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
    RSSItemDelivery,
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

    async def async_list_user_active_subscriptions(
        self,
        user_id: int,
        *,
        substack_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Return active subscriptions for a user, optionally filtered to Substack."""

        def _query() -> list[dict[str, Any]]:
            query = (
                RSSFeedSubscription.select(RSSFeedSubscription, RSSFeed, ChannelCategory)
                .join(RSSFeed)
                .switch(RSSFeedSubscription)
                .join(
                    ChannelCategory,
                    peewee.JOIN.LEFT_OUTER,
                    on=(RSSFeedSubscription.category == ChannelCategory.id),
                )
                .where(
                    (RSSFeedSubscription.user == user_id) & (RSSFeedSubscription.is_active == True)  # noqa: E712
                )
                .order_by(RSSFeedSubscription.created_at.desc())
            )
            if substack_only:
                query = query.where(RSSFeed.url.contains("substack.com"))

            result: list[dict[str, Any]] = []
            for row in query:
                item = model_to_dict(row) or {}
                feed = model_to_dict(row.feed) or {}
                item["feed"] = feed
                item["category_name"] = (
                    row.category.name if getattr(row, "category", None) else None
                )
                result.append(item)
            return result

        return await self._execute(
            _query,
            operation_name="list_user_active_rss_subscriptions",
            read_only=True,
        )

    async def async_get_subscription_by_feed(
        self, *, user_id: int, feed_id: int
    ) -> dict[str, Any] | None:
        """Return a user's subscription for a feed."""

        def _query() -> dict[str, Any] | None:
            row = (
                RSSFeedSubscription.select(RSSFeedSubscription, RSSFeed)
                .join(RSSFeed)
                .where(
                    (RSSFeedSubscription.user == user_id) & (RSSFeedSubscription.feed == feed_id)
                )
                .first()
            )
            if row is None:
                return None
            item = model_to_dict(row) or {}
            item["feed"] = model_to_dict(row.feed) or {}
            return item

        return await self._execute(
            _query, operation_name="get_rss_subscription_by_feed", read_only=True
        )

    async def async_get_subscription(
        self, *, user_id: int, subscription_id: int
    ) -> dict[str, Any] | None:
        """Return a user's subscription by subscription ID."""

        def _query() -> dict[str, Any] | None:
            row = (
                RSSFeedSubscription.select(RSSFeedSubscription, RSSFeed, ChannelCategory)
                .join(RSSFeed)
                .switch(RSSFeedSubscription)
                .join(
                    ChannelCategory,
                    peewee.JOIN.LEFT_OUTER,
                    on=(RSSFeedSubscription.category == ChannelCategory.id),
                )
                .where(
                    (RSSFeedSubscription.id == subscription_id)
                    & (RSSFeedSubscription.user == user_id)
                )
                .first()
            )
            if row is None:
                return None
            item = model_to_dict(row) or {}
            item["feed"] = model_to_dict(row.feed) or {}
            item["category_name"] = row.category.name if getattr(row, "category", None) else None
            return item

        return await self._execute(_query, operation_name="get_rss_subscription", read_only=True)

    async def async_set_subscription_active(self, subscription_id: int, *, is_active: bool) -> None:
        """Update subscription active state."""

        def _update() -> None:
            RSSFeedSubscription.update(
                is_active=is_active,
                updated_at=datetime.now(UTC),
            ).where(RSSFeedSubscription.id == subscription_id).execute()

        await self._execute(_update, operation_name="set_rss_subscription_active")

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

    async def async_list_delivery_targets(
        self,
        new_item_ids: list[int] | None,
    ) -> list[dict[str, Any]]:
        """Return undelivered item rows with subscriber IDs."""

        def _query() -> list[dict[str, Any]]:
            query = RSSFeedItem.select()
            if new_item_ids:
                query = query.where(RSSFeedItem.id.in_(new_item_ids))

            result: list[dict[str, Any]] = []
            for item in query.order_by(RSSFeedItem.published_at.desc()):
                subs = RSSFeedSubscription.select(RSSFeedSubscription.user).where(
                    (RSSFeedSubscription.feed == item.feed_id)
                    & (RSSFeedSubscription.is_active == True)  # noqa: E712
                )
                subscriber_ids: list[int] = []
                for sub in subs:
                    already = (
                        RSSItemDelivery.select()
                        .where(
                            (RSSItemDelivery.user == sub.user_id)
                            & (RSSItemDelivery.item == item.id)
                        )
                        .exists()
                    )
                    if not already:
                        subscriber_ids.append(sub.user_id)

                if not subscriber_ids:
                    continue
                item_dict = model_to_dict(item) or {}
                item_dict["subscriber_ids"] = subscriber_ids
                result.append(item_dict)
            return result

        return await self._execute(
            _query, operation_name="list_rss_delivery_targets", read_only=True
        )

    async def async_mark_item_delivered(self, *, user_id: int, item_id: int) -> None:
        """Create an RSS delivery record for a user and item."""

        def _insert() -> None:
            RSSItemDelivery.create(user=user_id, item=item_id)

        await self._execute(_insert, operation_name="mark_rss_item_delivered")

    async def async_update_feed_fetch_success(
        self,
        *,
        feed_id: int,
        title: str | None,
        description: str | None,
        site_url: str | None,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        """Update feed metadata after a successful poll."""

        def _update() -> None:
            now = datetime.now(UTC)
            RSSFeed.update(
                title=title,
                description=description,
                site_url=site_url,
                last_fetched_at=now,
                last_successful_at=now,
                etag=etag,
                last_modified=last_modified,
                fetch_error_count=0,
                last_error=None,
            ).where(RSSFeed.id == feed_id).execute()

        await self._execute(_update, operation_name="update_rss_feed_fetch_success")

    async def async_record_feed_fetch_error(
        self,
        *,
        feed_id: int,
        error: str,
        max_fetch_errors: int,
    ) -> None:
        """Increment RSS feed error counters and disable on threshold."""

        def _update() -> None:
            feed = RSSFeed.get_by_id(feed_id)
            error_count = feed.fetch_error_count + 1
            update_fields = {
                RSSFeed.fetch_error_count: error_count,
                RSSFeed.last_error: error[:500],
            }
            if error_count >= max_fetch_errors:
                update_fields[RSSFeed.is_active] = False
            RSSFeed.update(update_fields).where(RSSFeed.id == feed_id).execute()

        await self._execute(_update, operation_name="record_rss_feed_fetch_error")
