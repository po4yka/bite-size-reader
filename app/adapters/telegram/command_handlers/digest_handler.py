"""Channel digest command handlers (/digest, /channels, /subscribe, /unsubscribe)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import peewee

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.core.channel_utils import parse_channel_input
from app.db.models import Channel, ChannelSubscription
from app.services.digest_subscription_ops import (
    subscribe_channel_atomic,
    unsubscribe_channel_atomic,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.adapters.digest.digest_service import DigestService
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = logging.getLogger(__name__)


class DigestHandlerImpl(HandlerDependenciesMixin):
    """Implementation of channel digest commands."""

    @asynccontextmanager
    async def _digest_context(self, ctx: CommandExecutionContext) -> AsyncIterator[DigestService]:
        """Shared setup/teardown for digest commands."""
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

            yield service
            await llm_client.aclose()
        finally:
            await userbot.stop()

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
            async with self._digest_context(ctx) as service:
                result = await service.generate_digest(
                    user_id=ctx.uid,
                    correlation_id=ctx.correlation_id,
                    digest_type="on_demand",
                    lang="ru",
                )
                if result.errors:
                    errors_text = "\n".join(result.errors[:3])
                    await self._formatter.safe_reply(
                        ctx.message,
                        f"Digest completed with errors:\n{errors_text}",
                    )
        except FileNotFoundError:
            await self._formatter.safe_reply(
                ctx.message,
                "Userbot session not found.\n\nRun /init_session first to authenticate.",
            )
        except Exception as exc:
            logger.exception("digest_command_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"Digest failed: {exc}")

    async def handle_cdigest(self, ctx: CommandExecutionContext) -> None:
        """Handle /cdigest @channel_name -- single-channel unread digest."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "Channel digest is not enabled.\n\nSet `DIGEST_ENABLED=true` in your environment.",
            )
            return

        # Parse channel name
        parts = ctx.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await self._formatter.safe_reply(
                ctx.message,
                "Usage: `/cdigest @channel_name`",
            )
            return

        username, error = parse_channel_input(parts[1])
        if error:
            await self._formatter.safe_reply(ctx.message, error)
            return

        # Get or create channel record (no subscription required)
        channel, _ = Channel.get_or_create(
            username=username,
            defaults={"title": username, "is_active": True},
        )

        await self._formatter.safe_reply(ctx.message, f"Generating digest for @{username}...")

        try:
            async with self._digest_context(ctx) as service:
                result = await service.generate_channel_digest(
                    user_id=ctx.uid,
                    channel=channel,
                    correlation_id=ctx.correlation_id,
                    lang="ru",
                )
                if result.errors:
                    errors_text = "\n".join(result.errors[:3])
                    await self._formatter.safe_reply(
                        ctx.message,
                        f"Digest completed with errors:\n{errors_text}",
                    )
        except FileNotFoundError:
            await self._formatter.safe_reply(
                ctx.message,
                "Userbot session not found.\n\nRun /init_session first to authenticate.",
            )
        except Exception as exc:
            logger.exception("cdigest_command_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"Channel digest failed: {exc}")

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

        lines.append(f"\nTotal subscribed channels: {len(subs)}")

        # Warn about disabled channels the user is subscribed to
        disabled = [s for s in subs if not s.channel.is_active]
        if disabled:
            lines.append("\n**Disabled channels** (too many fetch errors):")
            for dsub in disabled:
                dch: Channel = dsub.channel
                lines.append(
                    f"  @{dch.username} -- {dch.fetch_error_count} errors. "
                    "Use `/unsubscribe` then `/subscribe` to re-enable."
                )

        await self._formatter.safe_reply(ctx.message, "\n".join(lines))

    _subscribe_atomic = staticmethod(subscribe_channel_atomic)

    async def handle_subscribe(self, ctx: CommandExecutionContext) -> None:
        """Handle /subscribe @channel_name command."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(ctx.message, "Channel digest is not enabled.")
            return

        parts = ctx.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await self._formatter.safe_reply(
                ctx.message,
                "Usage: `/subscribe @channel_name`",
            )
            return

        username, error = parse_channel_input(parts[1])
        if error:
            await self._formatter.safe_reply(ctx.message, error)
            return

        try:
            status = await self._db._safe_db_transaction(
                self._subscribe_atomic,
                ctx.uid,
                username,
                operation_name="subscribe_channel",
            )
        except peewee.IntegrityError:
            status = "already_subscribed"

        if status == "already_subscribed":
            await self._formatter.safe_reply(ctx.message, f"Already subscribed to @{username}.")
        elif status == "reactivated":
            await self._formatter.safe_reply(
                ctx.message, f"Reactivated subscription to @{username}."
            )
        else:
            await self._formatter.safe_reply(
                ctx.message,
                f"Subscribed to @{username}.\n\n"
                "Use `/digest` to generate a digest now, or wait for the daily delivery.",
            )
            logger.info(
                "digest_subscribed",
                extra={"uid": ctx.uid, "channel": username, "cid": ctx.correlation_id},
            )

    _unsubscribe_atomic = staticmethod(unsubscribe_channel_atomic)

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

        username, error = parse_channel_input(parts[1])
        if error:
            await self._formatter.safe_reply(ctx.message, error)
            return

        status = await self._db._safe_db_transaction(
            self._unsubscribe_atomic,
            ctx.uid,
            username,
            operation_name="unsubscribe_channel",
        )

        if status == "not_found":
            await self._formatter.safe_reply(ctx.message, f"Channel @{username} not found.")
        elif status == "not_subscribed":
            await self._formatter.safe_reply(ctx.message, f"Not subscribed to @{username}.")
        else:
            await self._formatter.safe_reply(ctx.message, f"Unsubscribed from @{username}.")
            logger.info(
                "digest_unsubscribed",
                extra={"uid": ctx.uid, "channel": username, "cid": ctx.correlation_id},
            )
