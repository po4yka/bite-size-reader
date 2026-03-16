"""Karakeep integration command handlers (/sync_karakeep).

This module handles the Karakeep bookmark sync integration,
including status checks and sync operations with rate limiting.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, ClassVar, cast

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.db.user_interactions import async_safe_update_user_interaction
from app.di.repositories import build_karakeep_sync_repository

if TYPE_CHECKING:
    from app.adapters.karakeep.sync.protocols import KarakeepSyncRepository
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = logging.getLogger(__name__)

# Rate limiting for Karakeep sync (5 minutes cooldown)
KARAKEEP_SYNC_COOLDOWN_SECONDS = 300


class KarakeepHandlerImpl(HandlerDependenciesMixin):
    """Implementation of Karakeep sync commands.

    Handles bidirectional sync between Bite-Size Reader and Karakeep
    bookmark manager, including status reporting and rate limiting.
    """

    # Class-level rate limiting for Karakeep sync
    _last_sync: ClassVar[dict[int, float]] = {}

    async def handle_sync_karakeep(self, ctx: CommandExecutionContext) -> None:
        """Handle /sync_karakeep command.

        Routes to appropriate subcommand handler based on arguments.

        Args:
            ctx: The command execution context.
        """
        logger.info(
            "command_sync_karakeep",
            extra={"uid": ctx.uid, "cid": ctx.correlation_id, "text": ctx.text},
        )

        # Check if Karakeep is enabled
        if not self._cfg.karakeep.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "⚠️ Karakeep sync is not enabled.\n\n"
                "Set `KARAKEEP_ENABLED=true` in your environment to enable.",
            )
            return

        if not self._cfg.karakeep.api_key:
            await self._formatter.safe_reply(
                ctx.message,
                "⚠️ Karakeep API key not configured.\n\nSet `KARAKEEP_API_KEY` in your environment.",
            )
            return

        # Parse subcommand
        parts = ctx.text.strip().split(maxsplit=1)
        subcommand = parts[1].lower() if len(parts) > 1 else "run"

        if subcommand == "status":
            await self._handle_karakeep_status(ctx)
        elif subcommand in ("run", "sync"):
            await self._handle_karakeep_sync(ctx)
        elif subcommand == "force":
            await self._handle_karakeep_sync(ctx, force=True)
        elif subcommand == "reset":
            await self._handle_karakeep_reset(ctx)
        else:
            await self._formatter.safe_reply(
                ctx.message,
                "**Karakeep Sync Commands:**\n\n"
                "`/sync_karakeep` - Run bidirectional sync\n"
                "`/sync_karakeep force` - Re-sync all (update tags/notes)\n"
                "`/sync_karakeep reset` - Clear sync records, then re-sync\n"
                "`/sync_karakeep status` - Show sync statistics\n",
            )

    async def _handle_karakeep_status(self, ctx: CommandExecutionContext) -> None:
        """Show Karakeep sync status.

        Args:
            ctx: The command execution context.
        """
        from app.adapters.karakeep import KarakeepSyncService

        try:
            karakeep_repo = cast("KarakeepSyncRepository", build_karakeep_sync_repository(self._db))
            service = KarakeepSyncService(
                api_url=self._cfg.karakeep.api_url,
                api_key=self._cfg.karakeep.api_key,
                sync_tag=self._cfg.karakeep.sync_tag,
                repository=karakeep_repo,
            )
            status = await service.get_sync_status()

            status_text = (
                "📊 **Karakeep Sync Status**\n\n"
                f"📤 BSR → Karakeep: {status['bsr_to_karakeep']} items\n"
                f"📥 Karakeep → BSR: {status['karakeep_to_bsr']} items\n"
                f"📈 Total synced: {status['total_synced']} items\n"
            )
            if status.get("last_sync_at"):
                status_text += f"🕐 Last sync: {status['last_sync_at']}\n"

            # Add auto-sync configuration info
            status_text += "\n**Auto Sync:**\n"
            if self._cfg.karakeep.auto_sync_enabled:
                status_text += (
                    f"✅ Enabled (every {self._cfg.karakeep.sync_interval_hours} hours)\n"
                )
            else:
                status_text += "❌ Disabled\n"

            await self._formatter.safe_reply(ctx.message, status_text)

        except Exception as exc:
            logger.exception("karakeep_status_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"⚠️ Failed to get sync status: {exc}")

    async def _handle_karakeep_sync(
        self, ctx: CommandExecutionContext, force: bool = False
    ) -> None:
        """Run Karakeep sync with rate limiting.

        Args:
            ctx: The command execution context.
            force: If True, re-sync all items (update tags/notes on existing bookmarks).
        """
        from app.adapters.karakeep import KarakeepSyncService

        # Rate limiting check
        last_sync = self._last_sync.get(ctx.uid)
        if last_sync is not None:
            elapsed = time.time() - last_sync
            if elapsed < KARAKEEP_SYNC_COOLDOWN_SECONDS:
                remaining = int(KARAKEEP_SYNC_COOLDOWN_SECONDS - elapsed)
                minutes = remaining // 60
                seconds = remaining % 60
                await self._formatter.safe_reply(
                    ctx.message,
                    f"Please wait {minutes}m {seconds}s before syncing again.\n\n"
                    "Use `/sync_karakeep status` to check current sync statistics.",
                )
                logger.info(
                    "karakeep_sync_rate_limited",
                    extra={
                        "uid": ctx.uid,
                        "remaining_seconds": remaining,
                        "cid": ctx.correlation_id,
                    },
                )
                return

        # Send initial message
        mode_label = " (force)" if force else ""
        await self._formatter.safe_reply(ctx.message, f"Starting Karakeep sync{mode_label}...")

        try:
            karakeep_repo = cast("KarakeepSyncRepository", build_karakeep_sync_repository(self._db))
            service = KarakeepSyncService(
                api_url=self._cfg.karakeep.api_url,
                api_key=self._cfg.karakeep.api_key,
                sync_tag=self._cfg.karakeep.sync_tag,
                repository=karakeep_repo,
            )

            result = await service.run_full_sync(user_id=ctx.uid, force=force)

            # Update rate limit timestamp
            self._last_sync[ctx.uid] = time.time()

            # Format result message
            bsr = result.bsr_to_karakeep
            kk = result.karakeep_to_bsr
            result_text = (
                "**Karakeep Sync Complete**\n\n"
                f"**BSR -> Karakeep:**\n"
                f"   Synced: {bsr.items_synced}\n"
                f"   Skipped: {bsr.items_skipped}\n"
            )
            # Show skip breakdown if there are skipped items
            if bsr.items_skipped > 0:
                result_text += (
                    f"      Already synced: {bsr.skipped_already_synced}\n"
                    f"      Already in Karakeep: {bsr.skipped_exists_in_target}\n"
                    f"      Hash errors: {bsr.skipped_hash_failed}\n"
                    f"      No URL: {bsr.skipped_no_url}\n"
                )
            result_text += (
                f"   Failed: {bsr.items_failed}\n\n"
                f"**Karakeep -> BSR:**\n"
                f"   Synced: {kk.items_synced}\n"
                f"   Skipped: {kk.items_skipped}\n"
                f"   Failed: {kk.items_failed}\n\n"
                f"Duration: {result.total_duration_seconds:.1f}s"
            )

            # Add errors if any
            all_errors = result.bsr_to_karakeep.errors + result.karakeep_to_bsr.errors
            if all_errors:
                result_text += f"\n\n⚠️ **Errors ({len(all_errors)}):**\n"
                for err in all_errors[:5]:  # Show max 5 errors
                    result_text += f"• {err[:100]}...\n" if len(err) > 100 else f"• {err}\n"

            await self._formatter.safe_reply(ctx.message, result_text)

            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="karakeep_sync_complete",
                    start_time=ctx.start_time,
                    logger_=logger,
                )

        except Exception as exc:
            logger.exception("karakeep_sync_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"Karakeep sync failed: {exc}")
            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="karakeep_sync_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=ctx.start_time,
                    logger_=logger,
                )

    async def _handle_karakeep_reset(self, ctx: CommandExecutionContext) -> None:
        """Reset all sync records and run a fresh sync.

        Args:
            ctx: The command execution context.
        """
        try:
            karakeep_repo = build_karakeep_sync_repository(self._db)
            deleted = await karakeep_repo.async_delete_all_sync_records()
            await self._formatter.safe_reply(
                ctx.message,
                f"Cleared {deleted} sync records. Running fresh sync...",
            )
            logger.info(
                "karakeep_sync_reset",
                extra={"uid": ctx.uid, "deleted": deleted, "cid": ctx.correlation_id},
            )
            # Reset rate limit so the subsequent sync isn't blocked
            self._last_sync.pop(ctx.uid, None)
            await self._handle_karakeep_sync(ctx, force=True)
        except Exception as exc:
            logger.exception("karakeep_reset_failed", extra={"cid": ctx.correlation_id})
            await self._formatter.safe_reply(ctx.message, f"Karakeep reset failed: {exc}")
