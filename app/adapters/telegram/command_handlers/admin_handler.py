"""Admin/maintenance command handlers (/dbinfo, /dbverify).

This module handles administrative commands for database inspection
and verification, including automated reprocessing of failed requests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.command_handlers.decorators import audit_command
from app.core.logging_utils import generate_correlation_id
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class AdminHandlerImpl:
    """Implementation of admin/maintenance commands (/dbinfo, /dbverify).

    These commands provide database inspection and verification capabilities
    for the bot owner to monitor system health and data integrity.
    """

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
    ) -> None:
        """Initialize the admin handler.

        Args:
            db: Database session manager for queries.
            response_formatter: Response formatter for sending messages.
            url_processor: URL processor for reprocessing failed requests.
        """
        self._db = db
        self._formatter = response_formatter
        self._url_processor = url_processor

    @audit_command("command_dbinfo")
    async def handle_dbinfo(self, ctx: CommandExecutionContext) -> None:
        """Handle /dbinfo command.

        Retrieves and displays a database overview including table counts,
        request statistics, and storage information.

        Args:
            ctx: The command execution context.
        """
        try:
            overview = self._db.get_database_overview()
        except Exception as exc:
            logger.exception("command_dbinfo_failed", extra={"cid": ctx.correlation_id})
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "⚠️ Unable to read database overview right now. Check bot logs for details.",
            )
            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="dbinfo_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=ctx.start_time,
                    logger_=logger,
                )
            return

        await self._formatter.send_db_overview(ctx.message, overview)

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type="dbinfo",
                start_time=ctx.start_time,
                logger_=logger,
            )

    @audit_command("command_dbverify")
    async def handle_dbverify(self, ctx: CommandExecutionContext) -> None:
        """Handle /dbverify command.

        Verifies database integrity by checking for:
        - Missing summaries for completed requests
        - Invalid summary JSON structures
        - Missing crawl results

        If issues are found, offers to reprocess affected URLs.

        Args:
            ctx: The command execution context.
        """
        try:
            verification = self._db.verify_processing_integrity()
        except Exception as exc:
            logger.exception("command_dbverify_failed", extra={"cid": ctx.correlation_id})
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "⚠️ Unable to verify database records right now. Check bot logs for details.",
            )
            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="dbverify_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=ctx.start_time,
                    logger_=logger,
                )
            return

        # Send verification results
        await self._formatter.send_db_verification(ctx.message, verification)

        # Process reprocessing entries
        await self._process_reprocess_entries(ctx, verification)

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type="dbverify",
                start_time=ctx.start_time,
                logger_=logger,
            )

    async def _process_reprocess_entries(
        self,
        ctx: CommandExecutionContext,
        verification: dict[str, Any],
    ) -> None:
        """Process entries that need reprocessing.

        Args:
            ctx: The command execution context.
            verification: The verification result dictionary.
        """
        posts_info = verification.get("posts") if isinstance(verification, dict) else None
        reprocess_entries = posts_info.get("reprocess") if isinstance(posts_info, dict) else []

        if not reprocess_entries:
            return

        urls_to_process: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for entry in reprocess_entries:
            if not isinstance(entry, dict):
                continue

            req_type = str(entry.get("type") or "").lower()
            if req_type == "url":
                url = entry.get("normalized_url") or entry.get("input_url")
                if not url:
                    skipped.append(entry)
                    continue
                urls_to_process.append(
                    {
                        "request_id": entry.get("request_id"),
                        "url": url,
                        "reasons": entry.get("reasons") or [],
                    }
                )
            else:
                skipped.append(entry)

        if urls_to_process or skipped:
            await self._formatter.send_db_reprocess_start(
                ctx.message, url_targets=urls_to_process, skipped=skipped
            )

        # Reprocess each URL
        failures: list[dict[str, Any]] = []
        for target in urls_to_process:
            url = target["url"]
            req_id = target.get("request_id")
            per_link_cid = generate_correlation_id()

            logger.info(
                "dbverify_reprocess_start",
                extra={
                    "request_id": req_id,
                    "url": url,
                    "cid": per_link_cid,
                    "cid_parent": ctx.correlation_id,
                },
            )

            try:
                await self._url_processor.handle_url_flow(
                    ctx.message,
                    url,
                    correlation_id=per_link_cid,
                )
            except Exception as exc:
                logger.exception(
                    "dbverify_reprocess_failed",
                    extra={
                        "request_id": req_id,
                        "url": url,
                        "cid": per_link_cid,
                        "cid_parent": ctx.correlation_id,
                    },
                )
                failure_entry = dict(target)
                failure_entry["error"] = str(exc)
                failures.append(failure_entry)

        if urls_to_process or skipped:
            await self._formatter.send_db_reprocess_complete(
                ctx.message,
                url_targets=urls_to_process,
                failures=failures,
                skipped=skipped,
            )
