"""Channel reader -- fetches posts and applies round-robin fair distribution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.db.models import Channel, ChannelPost, ChannelSubscription, DigestDelivery, _utcnow

if TYPE_CHECKING:
    from app.config import AppConfig

    from .userbot_client import UserbotClient

logger = logging.getLogger(__name__)


class ChannelReader:
    """Fetches posts from subscribed channels with fair distribution."""

    def __init__(self, cfg: AppConfig, userbot: UserbotClient) -> None:
        self._cfg = cfg
        self._userbot = userbot

    async def fetch_posts_for_user(
        self, user_id: int, max_posts: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch and persist posts from all active subscriptions for a user.

        Uses round-robin fair distribution: each channel gets an equal share,
        then remaining slots are filled from channels with more available posts.

        Args:
            user_id: Telegram user ID.
            max_posts: Override for max posts per digest.

        Returns:
            List of post dicts ready for analysis.
        """
        max_total = max_posts or self._cfg.digest.max_posts_per_digest

        subscriptions = list(
            ChannelSubscription.select()
            .join(Channel)
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
                Channel.is_active == True,  # noqa: E712
            )
        )

        if not subscriptions:
            logger.info("digest_no_subscriptions", extra={"uid": user_id})
            return []

        # Fetch posts per channel
        channel_posts: dict[int, list[dict[str, Any]]] = {}
        for sub in subscriptions:
            channel: Channel = sub.channel
            try:
                posts = await self._userbot.fetch_channel_posts(
                    channel.username,
                    hours_lookback=self._cfg.digest.hours_lookback,
                    min_length=self._cfg.digest.min_post_length,
                )
                for p in posts:
                    p["_channel_id"] = channel.channel_id or channel.id
                    p["_channel_username"] = channel.username
                self._persist_posts(channel, posts)
                self._update_channel_fetch_time(channel)
                channel_posts[channel.id] = posts
            except Exception:
                logger.exception(
                    "digest_channel_fetch_error",
                    extra={"channel": channel.username, "uid": user_id},
                )
                # Increment error count
                Channel.update(
                    fetch_error_count=Channel.fetch_error_count + 1,
                    last_error="fetch_failed",
                    updated_at=_utcnow(),
                ).where(Channel.id == channel.id).execute()
                continue

        if not channel_posts:
            return []

        # Round-robin fair distribution
        return self._fair_distribute(
            channel_posts, max_total, self._cfg.digest.max_posts_per_channel
        )

    async def fetch_posts_for_channel(
        self,
        channel: Channel,
        user_id: int,
        max_posts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch unread posts from a single channel for a user.

        'Unread' means the message_id is not present in any prior
        DigestDelivery.posts_json for this user.

        Args:
            channel: Channel record to fetch from.
            user_id: Telegram user ID (for delivery history lookup).
            max_posts: Override for max posts cap.

        Returns:
            List of unread post dicts, sorted by date desc, capped.
        """
        max_total = max_posts or self._cfg.digest.max_posts_per_digest

        posts = await self._userbot.fetch_channel_posts(
            channel.username,
            hours_lookback=self._cfg.digest.hours_lookback,
            min_length=self._cfg.digest.min_post_length,
        )
        for p in posts:
            p["_channel_id"] = channel.channel_id or channel.id
            p["_channel_username"] = channel.username
        self._persist_posts(channel, posts)
        self._update_channel_fetch_time(channel)

        # Filter out already-delivered posts
        delivered_ids = _get_delivered_message_ids(user_id)
        unread = [p for p in posts if p["message_id"] not in delivered_ids]

        # Sort by date desc, cap
        unread.sort(key=lambda p: p.get("date") or "", reverse=True)
        return unread[:max_total]

    @staticmethod
    def _fair_distribute(
        channel_posts: dict[int, list[dict[str, Any]]],
        max_total: int,
        max_per_channel: int | None = None,
    ) -> list[dict[str, Any]]:
        """Distribute posts fairly across channels.

        Each channel gets floor(max_total / num_channels) posts, capped by
        ``max_per_channel``. Remaining slots are filled round-robin from
        channels with extras.
        """
        num_channels = len(channel_posts)
        if num_channels == 0:
            return []

        fair_share = max_total // num_channels
        if max_per_channel is not None:
            fair_share = min(fair_share, max_per_channel)

        result: list[dict[str, Any]] = []
        overflow: list[dict[str, Any]] = []

        for _channel_id, posts in channel_posts.items():
            # Sort by date desc (most recent first)
            sorted_posts = sorted(posts, key=lambda p: p.get("date") or "", reverse=True)
            # Cap per channel
            if max_per_channel is not None:
                sorted_posts = sorted_posts[:max_per_channel]
            result.extend(sorted_posts[:fair_share])
            overflow.extend(sorted_posts[fair_share:])

        # Fill remaining slots from overflow
        remaining = max_total - len(result)
        if remaining > 0:
            result.extend(overflow[:remaining])

        return result

    @staticmethod
    def _persist_posts(channel: Channel, posts: list[dict[str, Any]]) -> None:
        """Persist fetched posts using get_or_create for idempotency."""
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

    @staticmethod
    def _update_channel_fetch_time(channel: Channel) -> None:
        """Update channel last_fetched_at and reset error count."""
        Channel.update(
            last_fetched_at=_utcnow(),
            fetch_error_count=0,
            last_error=None,
            updated_at=_utcnow(),
        ).where(Channel.id == channel.id).execute()


def _get_delivered_message_ids(user_id: int) -> set[int]:
    """Collect all message_ids from past digest deliveries for a user."""
    delivered: set[int] = set()
    for dd in DigestDelivery.select(DigestDelivery.posts_json).where(
        DigestDelivery.user == user_id,
    ):
        if dd.posts_json and isinstance(dd.posts_json, list):
            delivered.update(dd.posts_json)
    return delivered
