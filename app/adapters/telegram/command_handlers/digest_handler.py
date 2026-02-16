"""Channel digest command handlers (/digest, /channels, /subscribe, /unsubscribe)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.db.models import Channel, ChannelSubscription

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class DigestHandlerImpl:
    """Implementation of channel digest commands."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._formatter = response_formatter

    async def handle_digest(self, ctx: CommandExecutionContext) -> None:
        """Handle /digest command -- generate on-demand digest."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "Channel digest is not enabled.\n\nSet `DIGEST_ENABLED=true` in your environment.",
            )
            return

        await self._formatter.safe_reply(ctx.message, "Generating digest...")

        try:
            from pathlib import Path

            from app.adapters.digest.analyzer import DigestAnalyzer
            from app.adapters.digest.channel_reader import ChannelReader
            from app.adapters.digest.digest_service import DigestService
            from app.adapters.digest.formatter import DigestFormatter
            from app.adapters.digest.userbot_client import UserbotClient
            from app.adapters.openrouter.openrouter_client import OpenRouterClient

            session_dir = Path("/data")
            userbot = UserbotClient(self._cfg, session_dir)
            await userbot.start()

            try:
                llm_client = OpenRouterClient(
                    api_key=self._cfg.openrouter.api_key,
                    model=self._cfg.openrouter.model,
                    fallback_models=self._cfg.openrouter.fallback_models,
                )
                reader = ChannelReader(self._cfg, userbot)
                analyzer = DigestAnalyzer(self._cfg, llm_client)
                formatter = DigestFormatter()

                async def send_msg(user_id: int, text: str, reply_markup: object = None) -> None:
                    await self._formatter.safe_reply(ctx.message, text, reply_markup=reply_markup)

                service = DigestService(
                    cfg=self._cfg,
                    reader=reader,
                    analyzer=analyzer,
                    formatter=formatter,
                    send_message_func=send_msg,
                )

                result = await service.generate_digest(
                    user_id=ctx.uid,
                    correlation_id=ctx.correlation_id,
                    digest_type="on_demand",
                )

                if result.errors:
                    errors_text = "\n".join(result.errors[:3])
                    await self._formatter.safe_reply(
                        ctx.message,
                        f"Digest completed with errors:\n{errors_text}",
                    )

                await llm_client.aclose()
            finally:
                await userbot.stop()

        except FileNotFoundError:
            await self._formatter.safe_reply(
                ctx.message,
                "Userbot session not found.\n\nRun /init_session first to authenticate.",
            )
        except Exception as exc:
            logger.exception("digest_command_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"Digest failed: {exc}")

    async def handle_channels(self, ctx: CommandExecutionContext) -> None:
        """Handle /channels command -- list subscribed channels."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "Channel digest is not enabled.",
            )
            return

        subs = list(
            ChannelSubscription.select()
            .join(Channel)
            .where(
                ChannelSubscription.user == ctx.uid,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
        )

        if not subs:
            await self._formatter.safe_reply(
                ctx.message,
                "No channel subscriptions.\n\nUse `/subscribe @channel_name` to add a channel.",
            )
            return

        lines = ["**Subscribed Channels:**\n"]
        for sub in subs:
            ch: Channel = sub.channel
            status = "active" if ch.is_active else "paused"
            error_info = f" (errors: {ch.fetch_error_count})" if ch.fetch_error_count else ""
            lines.append(f"  @{ch.username} [{status}]{error_info}")

        lines.append(f"\n{len(subs)}/{self._cfg.digest.max_channels} slots used")
        await self._formatter.safe_reply(ctx.message, "\n".join(lines))

    async def handle_subscribe(self, ctx: CommandExecutionContext) -> None:
        """Handle /subscribe @channel_name command."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(ctx.message, "Channel digest is not enabled.")
            return

        # Parse channel name from text
        parts = ctx.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await self._formatter.safe_reply(
                ctx.message,
                "Usage: `/subscribe @channel_name`",
            )
            return

        raw_name = parts[1].strip().lstrip("@")
        if not raw_name:
            await self._formatter.safe_reply(ctx.message, "Please provide a channel name.")
            return

        # Check max channels limit
        active_count = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == ctx.uid,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active_count >= self._cfg.digest.max_channels:
            await self._formatter.safe_reply(
                ctx.message,
                f"Maximum channel limit reached ({self._cfg.digest.max_channels}).\n"
                "Use `/unsubscribe @channel` to remove one first.",
            )
            return

        # Get or create channel
        channel, _created = Channel.get_or_create(
            username=raw_name,
            defaults={"title": raw_name, "is_active": True},
        )

        # Check if already subscribed
        existing = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == ctx.uid,
                ChannelSubscription.channel == channel,
            )
            .first()
        )

        if existing:
            if existing.is_active:
                await self._formatter.safe_reply(ctx.message, f"Already subscribed to @{raw_name}.")
                return
            # Reactivate
            existing.is_active = True
            existing.save()
            await self._formatter.safe_reply(
                ctx.message, f"Reactivated subscription to @{raw_name}."
            )
            return

        ChannelSubscription.create(
            user=ctx.uid,
            channel=channel,
            is_active=True,
        )

        await self._formatter.safe_reply(
            ctx.message,
            f"Subscribed to @{raw_name}.\n\n"
            "Use `/digest` to generate a digest now, or wait for the daily delivery.",
        )
        logger.info(
            "digest_subscribed",
            extra={"uid": ctx.uid, "channel": raw_name, "cid": ctx.correlation_id},
        )

    async def handle_unsubscribe(self, ctx: CommandExecutionContext) -> None:
        """Handle /unsubscribe @channel_name command."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(ctx.message, "Channel digest is not enabled.")
            return

        parts = ctx.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await self._formatter.safe_reply(
                ctx.message,
                "Usage: `/unsubscribe @channel_name`",
            )
            return

        raw_name = parts[1].strip().lstrip("@")
        if not raw_name:
            await self._formatter.safe_reply(ctx.message, "Please provide a channel name.")
            return

        channel = Channel.get_or_none(Channel.username == raw_name)
        if not channel:
            await self._formatter.safe_reply(ctx.message, f"Channel @{raw_name} not found.")
            return

        sub = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.user == ctx.uid,
                ChannelSubscription.channel == channel,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .first()
        )

        if not sub:
            await self._formatter.safe_reply(ctx.message, f"Not subscribed to @{raw_name}.")
            return

        sub.is_active = False
        sub.save()

        await self._formatter.safe_reply(ctx.message, f"Unsubscribed from @{raw_name}.")
        logger.info(
            "digest_unsubscribed",
            extra={"uid": ctx.uid, "channel": raw_name, "cid": ctx.correlation_id},
        )
