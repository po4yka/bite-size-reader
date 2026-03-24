"""Backup management command handlers (/backup, /backups).

Lets users create and list backups via Telegram commands.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.adapters.telegram.command_handlers.decorators import combined_handler
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import UserBackup
from app.infrastructure.persistence.sqlite.backup_archive_service import create_backup_archive

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = get_logger(__name__)

_MAX_BACKUPS_PER_HOUR = 3
_MAX_LIST_COUNT = 5


class BackupHandler(HandlerDependenciesMixin):
    """Handle /backup and /backups commands."""

    @combined_handler("command_backup", "backup")
    async def handle_backup(self, ctx: CommandExecutionContext) -> None:
        """Handle /backup -- create a backup and send it as a document."""
        user_id = ctx.uid

        # Rate limit check
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        recent_count = (
            UserBackup.select()
            .where((UserBackup.user == user_id) & (UserBackup.created_at >= one_hour_ago))
            .count()
        )
        if recent_count >= _MAX_BACKUPS_PER_HOUR:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"Rate limit: maximum {_MAX_BACKUPS_PER_HOUR} backups per hour. "
                "Please try again later.",
            )
            return

        # Create backup record
        backup = UserBackup.create(
            user=user_id,
            type="manual",
            status="processing",
        )

        await ctx.response_formatter.safe_reply(
            ctx.message,
            "Creating backup... This may take a moment.",
        )

        try:
            create_backup_archive(user_id=user_id, backup_id=backup.id, db=self._db)

            # Reload to get updated fields
            backup = UserBackup.get_by_id(backup.id)

            if backup.status != "completed" or not backup.file_path:
                error_msg = backup.error or "Unknown error"
                await ctx.response_formatter.safe_reply(
                    ctx.message,
                    f"Backup failed: {error_msg}",
                )
                return

            # Send the ZIP file as a document
            file_size_mb = (backup.file_size_bytes or 0) / (1024 * 1024)
            caption = (
                f"Backup completed\nItems: {backup.items_count or 0}\nSize: {file_size_mb:.1f} MB"
            )
            await ctx.message.reply_document(
                document=backup.file_path,
                caption=caption,
            )

        except Exception as exc:
            logger.exception(
                "telegram_backup_failed",
                extra={"uid": user_id, "backup_id": backup.id, "error": str(exc)},
            )
            # Mark as failed if not already
            try:
                UserBackup.update(
                    status="failed",
                    error=str(exc)[:1000],
                ).where((UserBackup.id == backup.id) & (UserBackup.status != "completed")).execute()
            except Exception:
                pass
            await ctx.response_formatter.safe_reply(
                ctx.message,
                f"Backup failed: {exc}",
            )

    @combined_handler("command_backups", "backups")
    async def handle_backups(self, ctx: CommandExecutionContext) -> None:
        """Handle /backups -- list recent backups."""
        user_id = ctx.uid

        backups = list(
            UserBackup.select()
            .where(UserBackup.user == user_id)
            .order_by(UserBackup.created_at.desc())
            .limit(_MAX_LIST_COUNT)
        )

        if not backups:
            await ctx.response_formatter.safe_reply(
                ctx.message,
                "No backups yet. Use /backup to create one.",
            )
            return

        lines: list[str] = ["Your recent backups:"]
        for i, b in enumerate(backups, 1):
            size_str = _format_size(b.file_size_bytes)
            age_str = _format_age(b.created_at)
            lines.append(f"{i}. {b.type} - {size_str} - {b.status} - {age_str}")

        await ctx.response_formatter.safe_reply(
            ctx.message,
            "\n".join(lines),
        )


def _format_size(bytes_val: int | None) -> str:
    """Format file size for display."""
    if bytes_val is None:
        return "-"
    if bytes_val < 1024:
        return f"{bytes_val} B"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{bytes_val / (1024 * 1024):.1f} MB"


def _format_age(dt: datetime | None) -> str:
    """Format a datetime as a human-readable relative age."""
    if dt is None:
        return "unknown"
    now = datetime.now(UTC)
    # Handle naive datetimes from the DB
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"
