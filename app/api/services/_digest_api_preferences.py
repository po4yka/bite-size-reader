"""Preference and delivery history helpers for DigestAPIService."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.exceptions import ValidationError
from app.api.models.digest import DigestDeliveryResponse, DigestPreferenceResponse
from app.api.services._digest_api_shared import require_enabled
from app.infrastructure.persistence.sqlite.digest_store import SqliteDigestStore

if TYPE_CHECKING:
    from app.config.digest import ChannelDigestConfig


class DigestPreferenceService:
    """Preference and history operations for digest API callers."""

    def __init__(self, cfg: ChannelDigestConfig) -> None:
        self._cfg = cfg
        self._store = SqliteDigestStore()

    def get_preferences(self, user_id: int) -> DigestPreferenceResponse:
        require_enabled(self._cfg)
        preference = self._store.get_user_preference(user_id)

        def _value(user_value: Any, global_value: Any) -> tuple[Any, str]:
            if user_value is not None:
                return user_value, "user"
            return global_value, "global"

        delivery_time, delivery_time_source = _value(
            preference.delivery_time if preference else None,
            ",".join(self._cfg.digest_times),
        )
        timezone, timezone_source = _value(
            preference.timezone if preference else None,
            self._cfg.timezone,
        )
        hours_lookback, hours_lookback_source = _value(
            preference.hours_lookback if preference else None,
            self._cfg.hours_lookback,
        )
        max_posts, max_posts_source = _value(
            preference.max_posts_per_digest if preference else None,
            self._cfg.max_posts_per_digest,
        )
        min_relevance, min_relevance_source = _value(
            preference.min_relevance_score if preference else None,
            self._cfg.min_relevance_score,
        )

        return DigestPreferenceResponse(
            delivery_time=delivery_time,
            delivery_time_source=delivery_time_source,
            timezone=timezone,
            timezone_source=timezone_source,
            hours_lookback=hours_lookback,
            hours_lookback_source=hours_lookback_source,
            max_posts_per_digest=max_posts,
            max_posts_per_digest_source=max_posts_source,
            min_relevance_score=min_relevance,
            min_relevance_score_source=min_relevance_source,
        )

    def update_preferences(self, user_id: int, **fields: Any) -> DigestPreferenceResponse:
        require_enabled(self._cfg)
        delivery_time = fields.get("delivery_time")
        if delivery_time is not None:
            parts = delivery_time.split(":")
            if len(parts) != 2:
                raise ValidationError("delivery_time must be in HH:MM format")
            try:
                hour, minute = int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise ValidationError("delivery_time must contain valid integers") from exc
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValidationError("Invalid hour/minute in delivery_time")

        preference, created = self._store.get_or_create_user_preference(
            user_id,
            {
                "delivery_time": fields.get("delivery_time"),
                "timezone": fields.get("timezone"),
                "hours_lookback": fields.get("hours_lookback"),
                "max_posts_per_digest": fields.get("max_posts_per_digest"),
                "min_relevance_score": fields.get("min_relevance_score"),
            },
        )
        if not created:
            changed = False
            for key in (
                "delivery_time",
                "timezone",
                "hours_lookback",
                "max_posts_per_digest",
                "min_relevance_score",
            ):
                value = fields.get(key)
                if value is not None and getattr(preference, key) != value:
                    setattr(preference, key, value)
                    changed = True
            if changed:
                self._store.touch_preference(preference)

        return self.get_preferences(user_id)

    def list_deliveries(self, user_id: int, limit: int = 20, offset: int = 0) -> dict[str, object]:
        require_enabled(self._cfg)
        total = self._store.count_deliveries(user_id)
        deliveries = self._store.list_deliveries(user_id=user_id, limit=limit, offset=offset)
        items = [
            DigestDeliveryResponse(
                id=delivery.id,
                delivered_at=delivery.delivered_at,
                post_count=delivery.post_count,
                channel_count=delivery.channel_count,
                digest_type=delivery.digest_type,
            )
            for delivery in deliveries
        ]
        return {
            "deliveries": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
