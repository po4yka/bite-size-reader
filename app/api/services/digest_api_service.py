"""Service layer for Digest Mini App API.

Reuses subscribe/unsubscribe transaction logic from digest_handler.py
and preference merging with ChannelDigestConfig global defaults.
"""

from __future__ import annotations

import asyncio
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
from app.services.digest_subscription_ops import (
    subscribe_channel_atomic,
    unsubscribe_channel_atomic,
)

logger = logging.getLogger(__name__)
_background_digest_tasks: set[asyncio.Task[None]] = set()


def _track_background_task(task: asyncio.Task[None]) -> None:
    """Keep a strong reference for fire-and-forget tasks until completion."""
    _background_digest_tasks.add(task)

    def _on_done(done_task: asyncio.Task[None]) -> None:
        _background_digest_tasks.discard(done_task)

    task.add_done_callback(_on_done)


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
            "max_channels": None,
            "unlimited_channels": True,
        }

    def subscribe_channel(self, user_id: int, raw_username: str) -> dict[str, str]:
        """Subscribe to a channel. Returns {"status": "created"|"reactivated"|...}."""
        self._require_enabled()

        username, error = parse_channel_input(raw_username)
        if error:
            raise ValidationError(error)

        try:
            status = self._subscribe_atomic(user_id, username)
        except peewee.IntegrityError:
            status = "already_subscribed"

        return {"status": status, "username": username}

    _subscribe_atomic = staticmethod(subscribe_channel_atomic)

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

    _unsubscribe_atomic = staticmethod(unsubscribe_channel_atomic)

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

    def trigger_channel_digest(self, user_id: int, raw_channel_username: str) -> dict[str, str]:
        """Queue an on-demand digest generation for a single channel."""
        self._require_enabled()

        channel_username, error = parse_channel_input(str(raw_channel_username or ""))
        if error:
            raise ValidationError(error)

        correlation_id = str(uuid.uuid4())

        logger.info(
            "channel_digest_triggered_via_api",
            extra={"uid": user_id, "channel": channel_username, "cid": correlation_id},
        )

        return {
            "status": "queued",
            "channel": channel_username,
            "correlation_id": correlation_id,
        }

    async def enqueue_digest_trigger(self, *, user_id: int, correlation_id: str) -> None:
        """Dispatch digest generation in a background task."""
        task = asyncio.create_task(
            self._execute_digest_trigger(user_id=user_id, correlation_id=correlation_id)
        )
        _track_background_task(task)

    async def enqueue_channel_digest_trigger(
        self,
        *,
        user_id: int,
        correlation_id: str,
        channel_username: str,
    ) -> None:
        """Dispatch single-channel digest generation in a background task."""
        task = asyncio.create_task(
            self._execute_channel_digest_trigger(
                user_id=user_id,
                correlation_id=correlation_id,
                channel_username=channel_username,
            )
        )
        _track_background_task(task)

    async def _execute_digest_trigger(self, *, user_id: int, correlation_id: str) -> None:
        try:
            result = await self._run_digest_task(
                user_id=user_id,
                correlation_id=correlation_id,
                channel_username=None,
            )
            logger.info(
                "digest_api_job_complete",
                extra={
                    "uid": user_id,
                    "cid": correlation_id,
                    "posts": result.post_count,
                    "channels": result.channel_count,
                    "messages": result.messages_sent,
                    "errors": len(result.errors),
                },
            )
        except Exception:
            logger.exception("digest_api_job_failed", extra={"uid": user_id, "cid": correlation_id})
            return

    async def _execute_channel_digest_trigger(
        self,
        *,
        user_id: int,
        correlation_id: str,
        channel_username: str,
    ) -> None:
        try:
            result = await self._run_digest_task(
                user_id=user_id,
                correlation_id=correlation_id,
                channel_username=channel_username,
            )
            logger.info(
                "channel_digest_api_job_complete",
                extra={
                    "uid": user_id,
                    "channel": channel_username,
                    "cid": correlation_id,
                    "posts": result.post_count,
                    "channels": result.channel_count,
                    "messages": result.messages_sent,
                    "errors": len(result.errors),
                },
            )
        except Exception:
            logger.exception(
                "channel_digest_api_job_failed",
                extra={"uid": user_id, "channel": channel_username, "cid": correlation_id},
            )
            return

    async def _run_digest_task(
        self,
        *,
        user_id: int,
        correlation_id: str,
        channel_username: str | None,
    ) -> Any:
        """Build runtime dependencies and execute one digest task."""
        from pathlib import Path

        from pyrogram import Client as PyroClient

        from app.adapters.digest.analyzer import DigestAnalyzer
        from app.adapters.digest.channel_reader import ChannelReader
        from app.adapters.digest.digest_service import DigestService
        from app.adapters.digest.formatter import DigestFormatter
        from app.adapters.digest.userbot_client import UserbotClient
        from app.adapters.openrouter.openrouter_client import OpenRouterClient
        from app.config import load_config

        session_dir = Path("/data")
        app_cfg = load_config()
        userbot = UserbotClient(app_cfg, session_dir)
        llm_client: OpenRouterClient | None = None

        await userbot.start()
        try:
            llm_client = OpenRouterClient(
                api_key=app_cfg.openrouter.api_key,
                model=app_cfg.openrouter.model,
                fallback_models=app_cfg.openrouter.fallback_models,
            )
            reader = ChannelReader(app_cfg, userbot)
            analyzer = DigestAnalyzer(app_cfg, llm_client)
            formatter = DigestFormatter()

            bot = PyroClient(
                name=f"digest_api_sender_{correlation_id[:8]}",
                api_id=app_cfg.telegram.api_id,
                api_hash=app_cfg.telegram.api_hash,
                bot_token=app_cfg.telegram.bot_token,
                in_memory=True,
            )

            async with bot:

                async def _send_message(
                    target_user_id: int,
                    text: str,
                    reply_markup: Any = None,
                ) -> None:
                    await bot.send_message(
                        chat_id=target_user_id,
                        text=text,
                        reply_markup=reply_markup,
                    )

                service = DigestService(
                    cfg=app_cfg,
                    reader=reader,
                    analyzer=analyzer,
                    formatter=formatter,
                    send_message_func=_send_message,
                )

                if channel_username is None:
                    return await service.generate_digest(
                        user_id=user_id,
                        correlation_id=correlation_id,
                        digest_type="on_demand",
                        lang="ru",
                    )

                channel, _ = Channel.get_or_create(
                    username=channel_username,
                    defaults={"title": channel_username, "is_active": True},
                )
                return await service.generate_channel_digest(
                    user_id=user_id,
                    channel=channel,
                    correlation_id=correlation_id,
                    lang="ru",
                )
        finally:
            if llm_client is not None:
                await llm_client.aclose()
            await userbot.stop()
