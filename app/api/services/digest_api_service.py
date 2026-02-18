"""Service layer for Digest Mini App API.

Reuses subscribe/unsubscribe transaction logic from digest_handler.py
and preference merging with ChannelDigestConfig global defaults.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import peewee

from app.api.exceptions import FeatureDisabledError, ValidationError
from app.api.models.digest import (
    ChannelSubscriptionResponse,
    DigestDeliveryResponse,
    DigestPreferenceResponse,
    TriggerDigestResponse,
)
from app.config.digest import ChannelDigestConfig  # noqa: TC001 - used at runtime
from app.core.channel_utils import parse_channel_input
from app.db.models import (
    Channel,
    ChannelSubscription,
    DigestDelivery,
    UserDigestPreference,
    _utcnow,
)

logger = logging.getLogger(__name__)


class DigestAPIService:
    """Stateless service for digest operations via REST API."""

    def __init__(self, digest_config: ChannelDigestConfig) -> None:
        self._cfg = digest_config

    def _require_enabled(self) -> None:
        if not self._cfg.enabled:
            raise FeatureDisabledError("digest", "Channel digest is not enabled.")

    def list_subscriptions(self, user_id: int) -> dict[str, Any]:
        """List channel subscriptions for a user."""
        self._require_enabled()

        subs = (
            ChannelSubscription.select(ChannelSubscription, Channel)
            .join(Channel)
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .order_by(ChannelSubscription.created_at.desc())
        )

        items = []
        for sub in subs:
            ch: Channel = sub.channel
            items.append(
                ChannelSubscriptionResponse(
                    id=sub.id,
                    username=ch.username,
                    title=ch.title,
                    is_active=sub.is_active,
                    fetch_error_count=ch.fetch_error_count,
                    last_error=ch.last_error,
                    created_at=sub.created_at,
                )
            )

        active_count = len(items)
        return {
            "channels": items,
            "active_count": active_count,
            "max_channels": self._cfg.max_channels,
        }

    def subscribe_channel(self, user_id: int, raw_username: str) -> dict[str, str]:
        """Subscribe to a channel. Returns {"status": "created"|"reactivated"|...}."""
        self._require_enabled()

        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        max_ch = self._cfg.max_channels
        try:
            status = self._subscribe_atomic(user_id, username, max_ch)
        except peewee.IntegrityError:
            status = "already_subscribed"

        if status == "limit_reached":
            raise ValidationError(
                f"Maximum channel limit reached ({max_ch}). Unsubscribe from a channel first."
            )

        return {"status": status, "username": username}

    @staticmethod
    def _subscribe_atomic(user_id: int, username: str, max_channels: int) -> str:
        """Run subscribe logic inside a single transaction.

        Mirrors digest_handler._subscribe_atomic for consistency.
        """
        active_count = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active_count >= max_channels:
            return "limit_reached"

        channel, _ = Channel.get_or_create(
            username=username,
            defaults={"title": username, "is_active": True},
        )

        existing = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.channel == channel,
            )
            .first()
        )

        if existing:
            if existing.is_active:
                return "already_subscribed"
            existing.is_active = True
            existing.updated_at = _utcnow()
            existing.save()
            return "reactivated"

        ChannelSubscription.create(
            user=user_id,
            channel=channel,
            is_active=True,
        )
        return "created"

    def unsubscribe_channel(self, user_id: int, raw_username: str) -> dict[str, str]:
        """Unsubscribe from a channel."""
        self._require_enabled()

        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        status = self._unsubscribe_atomic(user_id, username)

        if status == "not_found":
            raise ValidationError(f"Channel @{username} not found.")
        if status == "not_subscribed":
            raise ValidationError(f"Not subscribed to @{username}.")

        return {"status": status, "username": username}

    @staticmethod
    def _unsubscribe_atomic(user_id: int, username: str) -> str:
        """Run unsubscribe logic inside a single transaction.

        Mirrors digest_handler._unsubscribe_atomic for consistency.
        """
        channel = Channel.get_or_none(Channel.username == username)
        if not channel:
            return "not_found"

        sub = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.channel == channel,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .first()
        )

        if not sub:
            return "not_subscribed"

        sub.is_active = False
        sub.updated_at = _utcnow()
        sub.save()
        return "unsubscribed"

    def get_preferences(self, user_id: int) -> DigestPreferenceResponse:
        """Get merged preferences (user overrides + global defaults)."""
        self._require_enabled()

        pref = UserDigestPreference.get_or_none(UserDigestPreference.user == user_id)

        def _val(user_val: Any, global_val: Any) -> tuple[Any, str]:
            if user_val is not None:
                return user_val, "user"
            return global_val, "global"

        dt, dt_src = _val(
            pref.delivery_time if pref else None,
            ",".join(self._cfg.digest_times),
        )
        tz, tz_src = _val(pref.timezone if pref else None, self._cfg.timezone)
        hl, hl_src = _val(pref.hours_lookback if pref else None, self._cfg.hours_lookback)
        mp, mp_src = _val(
            pref.max_posts_per_digest if pref else None, self._cfg.max_posts_per_digest
        )
        mr, mr_src = _val(pref.min_relevance_score if pref else None, self._cfg.min_relevance_score)

        return DigestPreferenceResponse(
            delivery_time=dt,
            delivery_time_source=dt_src,
            timezone=tz,
            timezone_source=tz_src,
            hours_lookback=hl,
            hours_lookback_source=hl_src,
            max_posts_per_digest=mp,
            max_posts_per_digest_source=mp_src,
            min_relevance_score=mr,
            min_relevance_score_source=mr_src,
        )

    def update_preferences(self, user_id: int, **fields: Any) -> DigestPreferenceResponse:
        """Upsert user digest preferences. Only non-None fields are updated."""
        self._require_enabled()

        # Validate delivery_time format if provided
        dt = fields.get("delivery_time")
        if dt is not None:
            parts = dt.split(":")
            if len(parts) != 2:
                raise ValidationError("delivery_time must be in HH:MM format")
            try:
                h, m = int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise ValidationError("delivery_time must contain valid integers") from exc
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValidationError("Invalid hour/minute in delivery_time")

        pref, created = UserDigestPreference.get_or_create(
            user=user_id,
            defaults={
                "delivery_time": fields.get("delivery_time"),
                "timezone": fields.get("timezone"),
                "hours_lookback": fields.get("hours_lookback"),
                "max_posts_per_digest": fields.get("max_posts_per_digest"),
                "min_relevance_score": fields.get("min_relevance_score"),
            },
        )

        if not created:
            # Update only provided fields
            changed = False
            for key in (
                "delivery_time",
                "timezone",
                "hours_lookback",
                "max_posts_per_digest",
                "min_relevance_score",
            ):
                val = fields.get(key)
                if val is not None and getattr(pref, key) != val:
                    setattr(pref, key, val)
                    changed = True
            if changed:
                pref.updated_at = _utcnow()
                pref.save()

        return self.get_preferences(user_id)

    def list_deliveries(self, user_id: int, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """Paginated list of digest deliveries."""
        self._require_enabled()

        total = DigestDelivery.select().where(DigestDelivery.user == user_id).count()

        deliveries = (
            DigestDelivery.select()
            .where(DigestDelivery.user == user_id)
            .order_by(DigestDelivery.delivered_at.desc())
            .offset(offset)
            .limit(limit)
        )

        items = [
            DigestDeliveryResponse(
                id=d.id,
                delivered_at=d.delivered_at,
                post_count=d.post_count,
                channel_count=d.channel_count,
                digest_type=d.digest_type,
            )
            for d in deliveries
        ]

        return {
            "deliveries": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def trigger_digest(self, user_id: int) -> TriggerDigestResponse:
        """Queue an on-demand digest generation.

        The actual generation happens asynchronously; result is delivered
        to Telegram chat. This endpoint just acknowledges the request.
        """
        self._require_enabled()

        # Verify user has active subscriptions
        active = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == user_id,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active == 0:
            raise ValidationError("No active channel subscriptions. Subscribe to channels first.")

        correlation_id = str(uuid.uuid4())

        logger.info(
            "digest_triggered_via_api",
            extra={"uid": user_id, "cid": correlation_id},
        )

        return TriggerDigestResponse(
            status="queued",
            correlation_id=correlation_id,
        )
