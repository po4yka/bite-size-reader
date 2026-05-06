"""Shared digest access for channels, posts, categories, and deliveries."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypeVar

from app.core.time_utils import utc_now
from app.db.models import (
    Channel,
    ChannelCategory,
    ChannelPost,
    ChannelPostAnalysis,
    ChannelSubscription,
    DigestDelivery,
    FeedItem,
    Source,
    Subscription,
    UserDigestPreference,
    _utcnow,
)

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from app.db.session import Database

T = TypeVar("T")


def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class DigestStore:
    """Centralized ORM access for digest runtime features."""

    def __init__(self, database: Database | None = None) -> None:
        self._db = database

    def _database(self) -> Database:
        if self._db is not None:
            return self._db

        from app.api.dependencies.database import get_session_manager

        return get_session_manager()

    async def async_list_active_subscriptions(self, user_id: int) -> list[ChannelSubscription]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(ChannelSubscription)
                        .options(
                            selectinload(ChannelSubscription.channel),
                            selectinload(ChannelSubscription.category),
                        )
                        .where(
                            ChannelSubscription.user_id == user_id,
                            ChannelSubscription.is_active.is_(True),
                        )
                        .order_by(ChannelSubscription.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )

    def list_active_subscriptions(self, user_id: int) -> list[Any]:
        return _run_sync(self.async_list_active_subscriptions(user_id))

    async def async_count_active_subscriptions(self, user_id: int) -> int:
        async with self._database().session() as session:
            return int(
                await session.scalar(
                    select(func.count(ChannelSubscription.id)).where(
                        ChannelSubscription.user_id == user_id,
                        ChannelSubscription.is_active.is_(True),
                    )
                )
                or 0
            )

    def count_active_subscriptions(self, user_id: int) -> int:
        return _run_sync(self.async_count_active_subscriptions(user_id))

    async def async_count_active_subscriptions_for_category(self, category: Any) -> int:
        async with self._database().session() as session:
            return int(
                await session.scalar(
                    select(func.count(ChannelSubscription.id)).where(
                        ChannelSubscription.category_id == category.id,
                        ChannelSubscription.is_active.is_(True),
                    )
                )
                or 0
            )

    def count_active_subscriptions_for_category(self, category: Any) -> int:
        return _run_sync(self.async_count_active_subscriptions_for_category(category))

    async def async_get_category_for_user(
        self, user_id: int, category_id: int
    ) -> ChannelCategory | None:
        async with self._database().session() as session:
            return await session.scalar(
                select(ChannelCategory).where(
                    ChannelCategory.id == category_id,
                    ChannelCategory.user_id == user_id,
                )
            )

    def get_category_for_user(self, user_id: int, category_id: int) -> Any | None:
        return _run_sync(self.async_get_category_for_user(user_id, category_id))

    async def async_list_categories(self, user_id: int) -> list[ChannelCategory]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(ChannelCategory)
                        .where(ChannelCategory.user_id == user_id)
                        .order_by(ChannelCategory.position, ChannelCategory.name)
                    )
                )
                .scalars()
                .all()
            )

    def list_categories(self, user_id: int) -> list[Any]:
        return _run_sync(self.async_list_categories(user_id))

    async def async_next_category_position(self, user_id: int) -> int:
        async with self._database().session() as session:
            max_pos = await session.scalar(
                select(func.max(ChannelCategory.position)).where(ChannelCategory.user_id == user_id)
            )
            return (max_pos or 0) + 1

    def next_category_position(self, user_id: int) -> int:
        return _run_sync(self.async_next_category_position(user_id))

    async def async_create_category(
        self, *, user_id: int, name: str, position: int
    ) -> ChannelCategory:
        async with self._database().transaction() as session:
            category = ChannelCategory(user_id=user_id, name=name, position=position)
            session.add(category)
            await session.flush()
            return category

    def create_category(self, *, user_id: int, name: str, position: int) -> Any:
        return _run_sync(self.async_create_category(user_id=user_id, name=name, position=position))

    async def async_save_model(self, instance: Any) -> None:
        if hasattr(instance, "updated_at"):
            instance.updated_at = _utcnow()
        async with self._database().transaction() as session:
            await session.merge(instance)

    def save_model(self, instance: Any) -> None:
        _run_sync(self.async_save_model(instance))

    async def async_delete_model(self, instance: Any) -> None:
        async with self._database().transaction() as session:
            persistent = await session.merge(instance)
            await session.delete(persistent)

    def delete_model(self, instance: Any) -> None:
        _run_sync(self.async_delete_model(instance))

    async def async_get_subscription_for_user(
        self, *, user_id: int, subscription_id: int
    ) -> ChannelSubscription | None:
        async with self._database().session() as session:
            return await session.scalar(
                select(ChannelSubscription)
                .options(
                    selectinload(ChannelSubscription.channel),
                    selectinload(ChannelSubscription.category),
                )
                .where(
                    ChannelSubscription.id == subscription_id,
                    ChannelSubscription.user_id == user_id,
                )
            )

    def get_subscription_for_user(self, *, user_id: int, subscription_id: int) -> Any | None:
        return _run_sync(
            self.async_get_subscription_for_user(
                user_id=user_id,
                subscription_id=subscription_id,
            )
        )

    async def async_list_category_subscriptions(
        self,
        *,
        user_id: int,
        subscription_ids: list[int],
    ) -> list[ChannelSubscription]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(ChannelSubscription)
                        .options(selectinload(ChannelSubscription.channel))
                        .where(
                            ChannelSubscription.id.in_(subscription_ids),
                            ChannelSubscription.user_id == user_id,
                        )
                    )
                )
                .scalars()
                .all()
            )

    def list_category_subscriptions(
        self,
        *,
        user_id: int,
        subscription_ids: list[int],
    ) -> list[Any]:
        return _run_sync(
            self.async_list_category_subscriptions(
                user_id=user_id,
                subscription_ids=subscription_ids,
            )
        )

    async def async_get_or_create_channel(
        self, username: str, *, title: str | None = None
    ) -> Channel:
        async with self._database().transaction() as session:
            channel = await session.scalar(select(Channel).where(Channel.username == username))
            if channel is not None:
                return channel

            channel = Channel(username=username, title=title or username, is_active=True)
            session.add(channel)
            await session.flush()
            return channel

    def get_or_create_channel(self, username: str, *, title: str | None = None) -> Any:
        return _run_sync(self.async_get_or_create_channel(username, title=title))

    async def async_update_channel_metadata(
        self, channel: Any, metadata: dict[str, Any]
    ) -> None:
        changed: dict[str, Any] = {}
        for field in ("title", "description", "member_count"):
            value = metadata.get(field)
            if value is not None and getattr(channel, field) != value:
                setattr(channel, field, value)
                changed[field] = value
        if changed:
            changed["updated_at"] = utc_now()
            async with self._database().transaction() as session:
                await session.execute(update(Channel).where(Channel.id == channel.id).values(**changed))

    def update_channel_metadata(self, channel: Any, metadata: dict[str, Any]) -> None:
        _run_sync(self.async_update_channel_metadata(channel, metadata))

    async def async_is_user_subscribed(self, *, user_id: int, channel: Any) -> bool:
        async with self._database().session() as session:
            return (
                await session.scalar(
                    select(ChannelSubscription.id).where(
                        ChannelSubscription.user_id == user_id,
                        ChannelSubscription.channel_id == channel.id,
                        ChannelSubscription.is_active.is_(True),
                    )
                )
                is not None
            )

    def is_user_subscribed(self, *, user_id: int, channel: Any) -> bool:
        return _run_sync(self.async_is_user_subscribed(user_id=user_id, channel=channel))

    async def async_get_channel_by_username(self, username: str) -> Channel | None:
        async with self._database().session() as session:
            return await session.scalar(select(Channel).where(Channel.username == username))

    def get_channel_by_username(self, username: str) -> Any | None:
        return _run_sync(self.async_get_channel_by_username(username))

    async def async_count_channel_posts(self, channel: Any) -> int:
        async with self._database().session() as session:
            return int(
                await session.scalar(
                    select(func.count(ChannelPost.id)).where(ChannelPost.channel_id == channel.id)
                )
                or 0
            )

    def count_channel_posts(self, channel: Any) -> int:
        return _run_sync(self.async_count_channel_posts(channel))

    async def async_list_channel_posts(
        self, channel: Any, *, limit: int, offset: int
    ) -> list[ChannelPost]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(ChannelPost)
                        .where(ChannelPost.channel_id == channel.id)
                        .order_by(ChannelPost.date.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

    def list_channel_posts(self, channel: Any, *, limit: int, offset: int) -> list[Any]:
        return _run_sync(self.async_list_channel_posts(channel, limit=limit, offset=offset))

    async def async_get_post_analysis(self, post: Any) -> ChannelPostAnalysis | None:
        async with self._database().session() as session:
            return await session.scalar(
                select(ChannelPostAnalysis).where(ChannelPostAnalysis.post_id == post.id)
            )

    def get_post_analysis(self, post: Any) -> Any | None:
        return _run_sync(self.async_get_post_analysis(post))

    async def async_list_deliveries(
        self, *, user_id: int, limit: int, offset: int
    ) -> list[DigestDelivery]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(DigestDelivery)
                        .where(DigestDelivery.user_id == user_id)
                        .order_by(DigestDelivery.delivered_at.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

    def list_deliveries(self, *, user_id: int, limit: int, offset: int) -> list[Any]:
        return _run_sync(self.async_list_deliveries(user_id=user_id, limit=limit, offset=offset))

    async def async_count_deliveries(self, user_id: int) -> int:
        async with self._database().session() as session:
            return int(
                await session.scalar(
                    select(func.count(DigestDelivery.id)).where(DigestDelivery.user_id == user_id)
                )
                or 0
            )

    def count_deliveries(self, user_id: int) -> int:
        return _run_sync(self.async_count_deliveries(user_id))

    async def async_get_user_preference(self, user_id: int) -> UserDigestPreference | None:
        async with self._database().session() as session:
            return await session.scalar(
                select(UserDigestPreference).where(UserDigestPreference.user_id == user_id)
            )

    def get_user_preference(self, user_id: int) -> Any | None:
        return _run_sync(self.async_get_user_preference(user_id))

    async def async_get_or_create_user_preference(
        self, user_id: int, defaults: dict[str, Any]
    ) -> tuple[UserDigestPreference, bool]:
        async with self._database().transaction() as session:
            preference = await session.scalar(
                select(UserDigestPreference).where(UserDigestPreference.user_id == user_id)
            )
            if preference is not None:
                return preference, False

            preference = UserDigestPreference(user_id=user_id, **defaults)
            session.add(preference)
            await session.flush()
            return preference, True

    def get_or_create_user_preference(
        self, user_id: int, defaults: dict[str, Any]
    ) -> tuple[Any, bool]:
        return _run_sync(self.async_get_or_create_user_preference(user_id, defaults))

    async def async_touch_preference(self, preference: Any) -> None:
        preference.updated_at = _utcnow()
        async with self._database().transaction() as session:
            await session.merge(preference)

    def touch_preference(self, preference: Any) -> None:
        _run_sync(self.async_touch_preference(preference))

    async def async_list_active_feed_subscriptions_with_channels(
        self, user_id: int
    ) -> list[ChannelSubscription]:
        async with self._database().session() as session:
            return list(
                (
                    await session.execute(
                        select(ChannelSubscription)
                        .join(Channel)
                        .options(selectinload(ChannelSubscription.channel))
                        .where(
                            ChannelSubscription.user_id == user_id,
                            ChannelSubscription.is_active.is_(True),
                            Channel.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )

    def list_active_feed_subscriptions_with_channels(self, user_id: int) -> list[Any]:
        return _run_sync(self.async_list_active_feed_subscriptions_with_channels(user_id))

    async def async_list_delivered_message_ids(self, user_id: int) -> set[int]:
        cutoff = utc_now() - timedelta(days=30)
        async with self._database().session() as session:
            rows = (
                await session.execute(
                    select(DigestDelivery.posts_json).where(
                        DigestDelivery.user_id == user_id,
                        DigestDelivery.delivered_at >= cutoff,
                    )
                )
            ).scalars()

            delivered: set[int] = set()
            for posts_json in rows:
                if posts_json and isinstance(posts_json, list):
                    delivered.update(int(post_id) for post_id in posts_json)
            return delivered

    def list_delivered_message_ids(self, user_id: int) -> set[int]:
        return _run_sync(self.async_list_delivered_message_ids(user_id))

    async def async_persist_posts(self, channel: Any, posts: list[dict[str, Any]]) -> None:
        async with self._database().transaction() as session:
            for post in posts:
                existing = await session.scalar(
                    select(ChannelPost).where(
                        ChannelPost.channel_id == channel.id,
                        ChannelPost.message_id == post["message_id"],
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    ChannelPost(
                        channel_id=channel.id,
                        message_id=post["message_id"],
                        text=post["text"],
                        media_type=post.get("media_type"),
                        date=post["date"],
                        views=post.get("views"),
                        forwards=post.get("forwards"),
                        url=post.get("url"),
                    )
                )

    def persist_posts(self, channel: Any, posts: list[dict[str, Any]]) -> None:
        _run_sync(self.async_persist_posts(channel, posts))

    async def async_mirror_posts_to_signal_sources(
        self,
        *,
        user_id: int,
        channel: Any,
        posts: list[dict[str, Any]],
    ) -> None:
        async with self._database().transaction() as session:
            source = await session.scalar(
                select(Source).where(
                    Source.kind == "telegram_channel",
                    Source.external_id == channel.username,
                )
            )
            if source is None:
                source = Source(kind="telegram_channel", external_id=channel.username)
                session.add(source)
                await session.flush()

            source.url = f"https://t.me/{channel.username}"
            source.title = channel.title
            source.description = channel.description
            source.is_active = channel.is_active
            source.fetch_error_count = channel.fetch_error_count
            source.last_error = channel.last_error
            source.last_fetched_at = channel.last_fetched_at
            source.metadata_json = {
                "channel_id": channel.channel_id,
                "member_count": channel.member_count,
            }
            source.legacy_channel_id = channel.id
            source.updated_at = _utcnow()

            subscription = await session.scalar(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.source_id == source.id,
                )
            )
            if subscription is None:
                session.add(
                    Subscription(user_id=user_id, source_id=source.id, is_active=True)
                )

            for post in posts:
                channel_post = await session.scalar(
                    select(ChannelPost).where(
                        ChannelPost.channel_id == channel.id,
                        ChannelPost.message_id == post["message_id"],
                    )
                )
                item = await session.scalar(
                    select(FeedItem).where(
                        FeedItem.source_id == source.id,
                        FeedItem.external_id == str(post["message_id"]),
                    )
                )
                if item is None:
                    item = FeedItem(source_id=source.id, external_id=str(post["message_id"]))
                    session.add(item)

                item.canonical_url = post.get("url")
                item.content_text = post.get("text")
                item.published_at = post.get("date")
                item.views = post.get("views")
                item.forwards = post.get("forwards")
                item.metadata_json = {"media_type": post.get("media_type")}
                item.legacy_channel_post_id = channel_post.id if channel_post else None
                item.updated_at = _utcnow()

    def mirror_posts_to_signal_sources(
        self,
        *,
        user_id: int,
        channel: Any,
        posts: list[dict[str, Any]],
    ) -> None:
        _run_sync(
            self.async_mirror_posts_to_signal_sources(
                user_id=user_id,
                channel=channel,
                posts=posts,
            )
        )

    async def async_update_channel_fetch_success(self, channel: Any) -> None:
        now = utc_now()
        async with self._database().transaction() as session:
            await session.execute(
                update(Channel)
                .where(Channel.id == channel.id)
                .values(
                    last_fetched_at=now,
                    fetch_error_count=0,
                    last_error=None,
                    updated_at=now,
                )
            )

    def update_channel_fetch_success(self, channel: Any) -> None:
        _run_sync(self.async_update_channel_fetch_success(channel))

    async def async_record_channel_fetch_error(
        self, channel: Any, error: str, *, max_errors: int
    ) -> bool:
        new_count = channel.fetch_error_count + 1
        disable = new_count >= max_errors
        values: dict[str, Any] = {
            "fetch_error_count": Channel.fetch_error_count + 1,
            "last_error": error,
            "updated_at": utc_now(),
        }
        if disable:
            values["is_active"] = False
        async with self._database().transaction() as session:
            await session.execute(update(Channel).where(Channel.id == channel.id).values(**values))
        return disable

    def record_channel_fetch_error(self, channel: Any, error: str, *, max_errors: int) -> bool:
        return _run_sync(
            self.async_record_channel_fetch_error(
                channel,
                error,
                max_errors=max_errors,
            )
        )

    async def async_get_channel_post(
        self, *, channel_id: int, message_id: int
    ) -> ChannelPost | None:
        async with self._database().session() as session:
            return await session.scalar(
                select(ChannelPost).where(
                    ChannelPost.channel_id == channel_id,
                    ChannelPost.message_id == message_id,
                )
            )

    def get_channel_post(self, *, channel_id: int, message_id: int) -> Any | None:
        return _run_sync(self.async_get_channel_post(channel_id=channel_id, message_id=message_id))

    async def async_find_cached_analysis(self, post: dict[str, Any]) -> dict[str, Any] | None:
        async with self._database().session() as session:
            channel_post = await session.scalar(
                select(ChannelPost).where(
                    ChannelPost.channel_id == post.get("_channel_id"),
                    ChannelPost.message_id == post["message_id"],
                )
            )
            if channel_post and channel_post.analyzed_at:
                existing = await session.scalar(
                    select(ChannelPostAnalysis).where(
                        ChannelPostAnalysis.post_id == channel_post.id
                    )
                )
                if existing:
                    return {
                        **post,
                        "real_topic": existing.real_topic,
                        "tldr": existing.tldr,
                        "key_insights": existing.key_insights or [],
                        "relevance_score": existing.relevance_score,
                        "content_type": existing.content_type,
                        "is_ad": False,
                    }
            return None

    def find_cached_analysis(self, post: dict[str, Any]) -> dict[str, Any] | None:
        return _run_sync(self.async_find_cached_analysis(post))

    async def async_persist_analysis(
        self, post: dict[str, Any], fields: dict[str, Any]
    ) -> None:
        async with self._database().transaction() as session:
            channel_post = await session.scalar(
                select(ChannelPost).where(
                    ChannelPost.channel_id == post.get("_channel_id"),
                    ChannelPost.message_id == post["message_id"],
                )
            )
            if channel_post is None:
                return

            existing = await session.scalar(
                select(ChannelPostAnalysis).where(ChannelPostAnalysis.post_id == channel_post.id)
            )
            if existing is None:
                session.add(
                    ChannelPostAnalysis(
                        post_id=channel_post.id,
                        real_topic=fields["real_topic"],
                        tldr=fields["tldr"],
                        key_insights=fields["key_insights"],
                        relevance_score=fields["relevance_score"],
                        content_type=fields["content_type"],
                    )
                )

            await session.execute(
                update(ChannelPost)
                .where(ChannelPost.id == channel_post.id)
                .values(analyzed_at=utc_now())
            )

    def persist_analysis(self, post: dict[str, Any], fields: dict[str, Any]) -> None:
        _run_sync(self.async_persist_analysis(post, fields))

    async def async_create_delivery(
        self,
        *,
        user_id: int,
        post_count: int,
        channel_count: int,
        digest_type: str,
        correlation_id: str,
        post_ids: list[int],
    ) -> None:
        async with self._database().transaction() as session:
            session.add(
                DigestDelivery(
                    user_id=user_id,
                    delivered_at=utc_now(),
                    post_count=post_count,
                    channel_count=channel_count,
                    digest_type=digest_type,
                    correlation_id=correlation_id,
                    posts_json=post_ids,
                )
            )

    def create_delivery(
        self,
        *,
        user_id: int,
        post_count: int,
        channel_count: int,
        digest_type: str,
        correlation_id: str,
        post_ids: list[int],
    ) -> None:
        _run_sync(
            self.async_create_delivery(
                user_id=user_id,
                post_count=post_count,
                channel_count=channel_count,
                digest_type=digest_type,
                correlation_id=correlation_id,
                post_ids=post_ids,
            )
        )

    async def async_get_users_with_subscriptions(self) -> list[int]:
        async with self._database().session() as session:
            rows = (
                await session.execute(
                    select(ChannelSubscription.user_id)
                    .where(ChannelSubscription.is_active.is_(True))
                    .distinct()
                )
            ).scalars()
            return list(rows)

    def get_users_with_subscriptions(self) -> list[int]:
        return _run_sync(self.async_get_users_with_subscriptions())
