"""Shared SQLite access for digest channels, posts, categories, and deliveries."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

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


class SqliteDigestStore:
    """Centralized ORM access for digest runtime features."""

    def list_active_subscriptions(self, user_id: int) -> list[Any]:
        return list(
            ChannelSubscription.select(ChannelSubscription, Channel)
            .join(Channel)
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .order_by(ChannelSubscription.created_at.desc())
        )

    def count_active_subscriptions(self, user_id: int) -> int:
        return (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )

    def count_active_subscriptions_for_category(self, category: Any) -> int:
        return (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.category == category,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )

    def get_category_for_user(self, user_id: int, category_id: int) -> Any | None:
        return ChannelCategory.get_or_none(
            ChannelCategory.id == category_id,
            ChannelCategory.user == user_id,
        )

    def list_categories(self, user_id: int) -> list[Any]:
        return list(
            ChannelCategory.select()
            .where(ChannelCategory.user == user_id)
            .order_by(ChannelCategory.position, ChannelCategory.name)
        )

    def next_category_position(self, user_id: int) -> int:
        import peewee

        max_pos = (
            ChannelCategory.select(peewee.fn.MAX(ChannelCategory.position))
            .where(ChannelCategory.user == user_id)
            .scalar()
        )
        return (max_pos or 0) + 1

    def create_category(self, *, user_id: int, name: str, position: int) -> Any:
        return ChannelCategory.create(user=user_id, name=name, position=position)

    def save_model(self, instance: Any) -> None:
        instance.save()

    def delete_model(self, instance: Any) -> None:
        instance.delete_instance()

    def get_subscription_for_user(self, *, user_id: int, subscription_id: int) -> Any | None:
        return ChannelSubscription.get_or_none(
            ChannelSubscription.id == subscription_id,
            ChannelSubscription.user == user_id,
        )

    def list_category_subscriptions(
        self,
        *,
        user_id: int,
        subscription_ids: list[int],
    ) -> list[Any]:
        return list(
            ChannelSubscription.select().where(
                ChannelSubscription.id.in_(subscription_ids),
                ChannelSubscription.user == user_id,
            )
        )

    def get_or_create_channel(self, username: str, *, title: str | None = None) -> Any:
        channel, _ = Channel.get_or_create(
            username=username,
            defaults={"title": title or username, "is_active": True},
        )
        return channel

    def update_channel_metadata(self, channel: Any, metadata: dict[str, Any]) -> None:
        changed = False
        for field in ("title", "description", "member_count"):
            value = metadata.get(field)
            if value is not None and getattr(channel, field) != value:
                setattr(channel, field, value)
                changed = True
        if changed:
            channel.save()

    def is_user_subscribed(self, *, user_id: int, channel: Any) -> bool:
        return (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.channel == channel,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .exists()
        )

    def get_channel_by_username(self, username: str) -> Any | None:
        return Channel.get_or_none(Channel.username == username)

    def count_channel_posts(self, channel: Any) -> int:
        return ChannelPost.select().where(ChannelPost.channel == channel).count()

    def list_channel_posts(self, channel: Any, *, limit: int, offset: int) -> list[Any]:
        return list(
            ChannelPost.select()
            .where(ChannelPost.channel == channel)
            .order_by(ChannelPost.date.desc())
            .offset(offset)
            .limit(limit)
        )

    def get_post_analysis(self, post: Any) -> Any | None:
        return ChannelPostAnalysis.get_or_none(ChannelPostAnalysis.post == post)

    def list_deliveries(self, *, user_id: int, limit: int, offset: int) -> list[Any]:
        return list(
            DigestDelivery.select()
            .where(DigestDelivery.user == user_id)
            .order_by(DigestDelivery.delivered_at.desc())
            .offset(offset)
            .limit(limit)
        )

    def count_deliveries(self, user_id: int) -> int:
        return DigestDelivery.select().where(DigestDelivery.user == user_id).count()

    def get_user_preference(self, user_id: int) -> Any | None:
        return UserDigestPreference.get_or_none(UserDigestPreference.user == user_id)

    def get_or_create_user_preference(
        self, user_id: int, defaults: dict[str, Any]
    ) -> tuple[Any, bool]:
        return UserDigestPreference.get_or_create(user=user_id, defaults=defaults)

    def touch_preference(self, preference: Any) -> None:
        preference.updated_at = _utcnow()
        preference.save()

    def list_active_feed_subscriptions_with_channels(self, user_id: int) -> list[Any]:
        return list(
            ChannelSubscription.select()
            .join(Channel)
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
                Channel.is_active == True,  # noqa: E712
            )
        )

    def list_delivered_message_ids(self, user_id: int) -> set[int]:
        cutoff = utc_now() - timedelta(days=30)
        delivered: set[int] = set()
        for delivery in DigestDelivery.select(DigestDelivery.posts_json).where(
            DigestDelivery.user == user_id,
            DigestDelivery.delivered_at >= cutoff,
        ):
            if delivery.posts_json and isinstance(delivery.posts_json, list):
                delivered.update(delivery.posts_json)
        return delivered

    def persist_posts(self, channel: Any, posts: list[dict[str, Any]]) -> None:
        for post in posts:
            ChannelPost.get_or_create(
                channel=channel,
                message_id=post["message_id"],
                defaults={
                    "text": post["text"],
                    "media_type": post.get("media_type"),
                    "date": post["date"],
                    "views": post.get("views"),
                    "forwards": post.get("forwards"),
                    "url": post.get("url"),
                },
            )

    def mirror_posts_to_signal_sources(
        self,
        *,
        user_id: int,
        channel: Any,
        posts: list[dict[str, Any]],
    ) -> None:
        source, _created = Source.get_or_create(
            kind="telegram_channel",
            external_id=channel.username,
            defaults={
                "url": f"https://t.me/{channel.username}",
                "title": channel.title,
                "description": channel.description,
                "is_active": channel.is_active,
                "fetch_error_count": channel.fetch_error_count,
                "last_error": channel.last_error,
                "last_fetched_at": channel.last_fetched_at,
                "metadata_json": {
                    "channel_id": channel.channel_id,
                    "member_count": channel.member_count,
                },
                "legacy_channel": channel.id,
            },
        )
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
        source.legacy_channel = channel.id
        source.save()
        Subscription.get_or_create(
            user=user_id,
            source=source.id,
            defaults={"is_active": True},
        )
        for post in posts:
            channel_post = ChannelPost.get_or_none(
                ChannelPost.channel == channel,
                ChannelPost.message_id == post["message_id"],
            )
            item, _item_created = FeedItem.get_or_create(
                source=source.id,
                external_id=str(post["message_id"]),
                defaults={
                    "canonical_url": post.get("url"),
                    "content_text": post.get("text"),
                    "published_at": post.get("date"),
                    "views": post.get("views"),
                    "forwards": post.get("forwards"),
                    "metadata_json": {"media_type": post.get("media_type")},
                    "legacy_channel_post": channel_post.id if channel_post else None,
                },
            )
            item.canonical_url = post.get("url")
            item.content_text = post.get("text")
            item.published_at = post.get("date")
            item.views = post.get("views")
            item.forwards = post.get("forwards")
            item.metadata_json = {"media_type": post.get("media_type")}
            if channel_post:
                item.legacy_channel_post = channel_post.id
            item.save()

    def update_channel_fetch_success(self, channel: Any) -> None:
        Channel.update(
            last_fetched_at=utc_now(),
            fetch_error_count=0,
            last_error=None,
            updated_at=utc_now(),
        ).where(Channel.id == channel.id).execute()

    def record_channel_fetch_error(self, channel: Any, error: str, *, max_errors: int) -> bool:
        new_count = channel.fetch_error_count + 1
        disable = new_count >= max_errors
        update_fields: dict[str, object] = {
            "fetch_error_count": Channel.fetch_error_count + 1,
            "last_error": error,
            "updated_at": utc_now(),
        }
        if disable:
            update_fields["is_active"] = False
        Channel.update(**update_fields).where(Channel.id == channel.id).execute()
        return disable

    def get_channel_post(self, *, channel_id: int, message_id: int) -> Any | None:
        return (
            ChannelPost.select()
            .join(Channel)
            .where(Channel.id == channel_id, ChannelPost.message_id == message_id)
            .first()
        )

    def find_cached_analysis(self, post: dict[str, Any]) -> dict[str, Any] | None:
        channel_post = (
            ChannelPost.select()
            .where(
                ChannelPost.channel == post.get("_channel_id"),
                ChannelPost.message_id == post["message_id"],
            )
            .first()
        )
        if channel_post and channel_post.analyzed_at:
            existing = (
                ChannelPostAnalysis.select().where(ChannelPostAnalysis.post == channel_post).first()
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

    def persist_analysis(self, post: dict[str, Any], fields: dict[str, Any]) -> None:
        channel_post = (
            ChannelPost.select()
            .where(
                ChannelPost.channel == post.get("_channel_id"),
                ChannelPost.message_id == post["message_id"],
            )
            .first()
        )
        if channel_post:
            ChannelPostAnalysis.get_or_create(
                post=channel_post,
                defaults={
                    "real_topic": fields["real_topic"],
                    "tldr": fields["tldr"],
                    "key_insights": fields["key_insights"],
                    "relevance_score": fields["relevance_score"],
                    "content_type": fields["content_type"],
                },
            )
            ChannelPost.update(analyzed_at=utc_now()).where(
                ChannelPost.id == channel_post.id
            ).execute()

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
        DigestDelivery.create(
            user=user_id,
            delivered_at=utc_now(),
            post_count=post_count,
            channel_count=channel_count,
            digest_type=digest_type,
            correlation_id=correlation_id,
            posts_json=post_ids,
        )

    def get_users_with_subscriptions(self) -> list[int]:
        rows = (
            ChannelSubscription.select(ChannelSubscription.user)
            .where(ChannelSubscription.is_active == True)  # noqa: E712
            .distinct()
        )
        return [row.user_id for row in rows]
