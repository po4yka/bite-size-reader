"""Admin/maintenance command handlers (/admin, /dbinfo, /dbverify).

This module handles administrative commands for database inspection
and verification, including automated reprocessing of failed requests.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

import peewee

from app.adapters.telegram.command_handlers.decorators import audit_command
from app.core.logging_utils import generate_correlation_id, get_logger
from app.core.time_utils import UTC
from app.db.models import ImportJob, Request, Summary, User
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


class AdminHandler:
    """Implementation of admin/maintenance commands (/admin, /dbinfo, /dbverify).

    These commands provide database inspection and verification capabilities
    for the bot owner to monitor system health and data integrity.
    """

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        url_handler: URLHandler | None = None,
    ) -> None:
        self._db = db
        self._formatter = response_formatter
        self._url_processor = url_processor
        self._url_handler = url_handler

    @audit_command("command_admin")
    async def handle_admin(self, ctx: CommandExecutionContext) -> None:
        """Handle /admin command with subcommands.

        Subcommands:
            (none) - Show overview stats (users, summaries, requests).
            jobs   - Show background job / pipeline status.
            errors - Show recent error summary (last 24h).

        Args:
            ctx: The command execution context.
        """
        subcommand = self._parse_admin_subcommand(ctx.text)

        try:
            if subcommand == "jobs":
                reply = self._build_jobs_reply()
            elif subcommand == "errors":
                reply = self._build_errors_reply()
            else:
                reply = self._build_overview_reply()
        except Exception as exc:
            logger.exception("command_admin_failed", extra={"cid": ctx.correlation_id})
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "Unable to fetch admin stats right now. Check bot logs for details.",
            )
            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="admin_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=ctx.start_time,
                    logger_=logger,
                )
            return

        await ctx.response_formatter.safe_reply(ctx.message, reply)

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type=f"admin_{subcommand or 'overview'}",
                start_time=ctx.start_time,
                logger_=logger,
            )

    # ------------------------------------------------------------------
    # /admin subcommand helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_admin_subcommand(text: str) -> str | None:
        """Extract the subcommand token after ``/admin``.

        Returns ``None`` when no recognised subcommand is present.
        """
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2:
            return None
        sub = parts[1].strip().lower()
        if sub in ("jobs", "errors"):
            return sub
        return None

    @staticmethod
    def _build_overview_reply() -> str:
        """Build the default /admin overview message."""
        user_count = User.select().count()
        summary_count = Summary.select().count()
        total_requests = Request.select().count()
        pending_requests = Request.select().where(Request.status == "pending").count()

        now = _dt.datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        failed_today = (
            Request.select()
            .where(
                (Request.status == "error") & (Request.created_at >= today_start),
            )
            .count()
        )

        return (
            "Admin Overview:\n"
            f"Users: {user_count:,}\n"
            f"Total summaries: {summary_count:,}\n"
            f"Total requests: {total_requests:,}\n"
            f"Pending requests: {pending_requests:,}\n"
            f"Failed today: {failed_today:,}"
        )

    @staticmethod
    def _build_jobs_reply() -> str:
        """Build the /admin jobs message."""
        now = _dt.datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Pipeline (Request) stats
        pending = Request.select().where(Request.status == "pending").count()
        processing = Request.select().where(Request.status == "processing").count()
        completed_today = (
            Request.select()
            .where(
                (Request.status == "completed") & (Request.created_at >= today_start),
            )
            .count()
        )
        failed_today = (
            Request.select()
            .where(
                (Request.status == "error") & (Request.created_at >= today_start),
            )
            .count()
        )

        # ImportJob stats
        import_active = (
            ImportJob.select().where(ImportJob.status.in_(["pending", "processing"])).count()
        )
        import_completed_today = (
            ImportJob.select()
            .where(
                (ImportJob.status == "completed") & (ImportJob.created_at >= today_start),
            )
            .count()
        )

        return (
            "Pipeline Status:\n"
            f"Pending: {pending} | Processing: {processing}\n"
            f"Completed today: {completed_today} | Failed: {failed_today}\n"
            "\n"
            "Import Jobs:\n"
            f"Active: {import_active} | Completed today: {import_completed_today}"
        )

    @staticmethod
    def _build_errors_reply() -> str:
        """Build the /admin errors message."""
        now = _dt.datetime.now(UTC)
        cutoff = now - _dt.timedelta(hours=24)

        error_rows = (
            Request.select(Request.error_type, peewee.fn.COUNT(Request.id).alias("cnt"))
            .where(
                (Request.status == "error") & (Request.created_at >= cutoff),
            )
            .group_by(Request.error_type)
            .order_by(peewee.fn.COUNT(Request.id).desc())
            .dicts()
        )

        if not error_rows:
            return "Recent Errors (last 24h):\nNo errors recorded."

        lines = ["Recent Errors (last 24h):"]
        for row in error_rows:
            label = row.get("error_type") or "unknown"
            lines.append(f"{label}: {row['cnt']}")

        # Latest failure
        latest = (
            Request.select()
            .where(
                (Request.status == "error") & (Request.created_at >= cutoff),
            )
            .order_by(Request.created_at.desc())
            .first()
        )

        if latest is not None:
            url = latest.input_url or latest.normalized_url or "N/A"
            error_msg = latest.error_message or "N/A"
            # Compute relative time
            delta = now - latest.created_at.replace(tzinfo=UTC)
            if delta.total_seconds() < 3600:
                ago = f"{int(delta.total_seconds() / 60)}m ago"
            else:
                ago = f"{int(delta.total_seconds() / 3600)}h ago"
            lines.append("")
            lines.append("Latest failure:")
            lines.append(f"URL: {url}")
            lines.append(f"Error: {error_msg} ({ago})")

        return "\n".join(lines)

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
            # Limit verification to the last 1000 records to prevent memory exhaustion
            # and ensure the command remains responsive.
            verification = self._db.verify_processing_integrity(limit=1000)
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
                if self._url_handler is not None:
                    await self._url_handler.handle_single_url(
                        message=ctx.message,
                        url=url,
                        correlation_id=per_link_cid,
                        interaction_id=ctx.interaction_id,
                    )
                else:
                    from app.adapters.content.url_flow_models import URLFlowRequest

                    await self._url_processor.handle_url_flow(
                        URLFlowRequest(
                            message=ctx.message, url_text=url, correlation_id=per_link_cid
                        )
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
