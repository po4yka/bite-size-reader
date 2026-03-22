"""Channel subscription and preview helpers for DigestAPIService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.api.exceptions import ValidationError
from app.api.models.digest import (
    ChannelPostResponse,
    ChannelSubscriptionResponse,
    PostAnalysisResponse,
    ResolveChannelResponse,
)
from app.api.services._digest_api_shared import require_enabled
from app.core.channel_utils import parse_channel_input
from app.db.models import (
    Channel,
    ChannelCategory,
    ChannelPost,
    ChannelPostAnalysis,
    ChannelSubscription,
)
from app.infrastructure.persistence.sqlite.digest_subscription_ops import (
    subscribe_channel_atomic,
    unsubscribe_channel_atomic,
)

if TYPE_CHECKING:
    from app.config.digest import ChannelDigestConfig


class DigestChannelService:
    """Channel-facing digest operations."""

    _subscribe_atomic = staticmethod(subscribe_channel_atomic)
    _unsubscribe_atomic = staticmethod(unsubscribe_channel_atomic)

    def __init__(self, cfg: ChannelDigestConfig) -> None:
        self._cfg = cfg

    def list_subscriptions(self, user_id: int) -> dict[str, object]:
        require_enabled(self._cfg)

        subscriptions = (
            ChannelSubscription.select(ChannelSubscription, Channel)
            .join(Channel)
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .order_by(ChannelSubscription.created_at.desc())
        )

        items: list[ChannelSubscriptionResponse] = []
        for subscription in subscriptions:
            channel: Channel = subscription.channel
            category_id = subscription.category_id
            category_name = None
            if category_id is not None:
                category = ChannelCategory.get_or_none(ChannelCategory.id == category_id)
                category_name = category.name if category else None
            items.append(
                ChannelSubscriptionResponse(
                    id=subscription.id,
                    username=channel.username,
                    title=channel.title,
                    is_active=subscription.is_active,
                    fetch_error_count=channel.fetch_error_count,
                    last_error=channel.last_error,
                    category_id=category_id,
                    category_name=category_name,
                    created_at=subscription.created_at,
                )
            )

        return {
            "channels": items,
            "active_count": len(items),
            "max_channels": None,
            "unlimited_channels": True,
        }

    def subscribe_channel(self, user_id: int, raw_username: str) -> dict[str, str]:
        require_enabled(self._cfg)
        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        try:
            status = self._subscribe_atomic(user_id, username)
        except peewee.IntegrityError:
            status = "already_subscribed"
        return {"status": status, "username": username}

    def unsubscribe_channel(self, user_id: int, raw_username: str) -> dict[str, str]:
        require_enabled(self._cfg)
        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        status = self._unsubscribe_atomic(user_id, username)
        if status == "not_found":
            raise ValidationError(f"Channel @{username} not found.")
        if status == "not_subscribed":
            raise ValidationError(f"Not subscribed to @{username}.")
        return {"status": status, "username": username}

    async def resolve_channel(self, user_id: int, raw_username: str) -> ResolveChannelResponse:
        require_enabled(self._cfg)
        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        from pathlib import Path

        from app.adapters.digest.userbot_client import UserbotClient
        from app.config import load_config

        app_cfg = load_config()
        userbot = UserbotClient(app_cfg, Path("/data"))
        await userbot.start()
        try:
            metadata = await userbot.resolve_channel(username)
        finally:
            await userbot.stop()

        channel, _ = Channel.get_or_create(
            username=username,
            defaults={"title": metadata.get("title"), "is_active": True},
        )
        changed = False
        for field in ("title", "description", "member_count"):
            value = metadata.get(field)
            if value is not None and getattr(channel, field) != value:
                setattr(channel, field, value)
                changed = True
        if changed:
            channel.save()

        is_subscribed = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.channel == channel,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .exists()
        )

        return ResolveChannelResponse(
            username=metadata.get("username", username),
            title=metadata.get("title"),
            description=metadata.get("description"),
            member_count=metadata.get("member_count"),
            is_subscribed=is_subscribed,
        )

    def list_channel_posts(
        self,
        user_id: int,
        raw_username: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, object]:
        require_enabled(self._cfg)
        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        channel = Channel.get_or_none(Channel.username == username)
        if channel is None:
            raise ValidationError(f"Channel @{username} not found.")

        subscription_exists = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.channel == channel,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .exists()
        )
        if not subscription_exists:
            raise ValidationError(f"Not subscribed to @{username}.")

        total = ChannelPost.select().where(ChannelPost.channel == channel).count()
        posts = (
            ChannelPost.select()
            .where(ChannelPost.channel == channel)
            .order_by(ChannelPost.date.desc())
            .offset(offset)
            .limit(limit)
        )

        items: list[ChannelPostResponse] = []
        for post in posts:
            analysis_row = ChannelPostAnalysis.get_or_none(ChannelPostAnalysis.post == post)
            analysis = None
            if analysis_row:
                analysis = PostAnalysisResponse(
                    real_topic=analysis_row.real_topic,
                    tldr=analysis_row.tldr,
                    relevance_score=analysis_row.relevance_score,
                    content_type=analysis_row.content_type,
                )

            items.append(
                ChannelPostResponse(
                    message_id=post.message_id,
                    text=post.text[:500],
                    date=post.date,
                    views=post.views,
                    forwards=post.forwards,
                    media_type=post.media_type,
                    url=post.url,
                    analysis=analysis,
                )
            )

        return {
            "posts": items,
            "total": total,
            "channel_username": username,
        }
