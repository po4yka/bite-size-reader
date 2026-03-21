"""SQLite implementation of backup repository.

This adapter handles persistence for user backup archives.
"""

from __future__ import annotations

from typing import Any

from app.core.logging_utils import get_logger
from app.db.models import UserBackup, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

logger = get_logger(__name__)


class SqliteBackupRepositoryAdapter(SqliteBaseRepository):
    """Adapter for user backup CRUD operations."""

    async def async_create_backup(
        self,
        user_id: int,
        type: str = "manual",
    ) -> dict[str, Any]:
        """Create a new backup record and return it as a dict."""

        def _insert() -> dict[str, Any]:
            backup = UserBackup.create(
                user=user_id,
                type=type,
                status="pending",
            )
            d = model_to_dict(backup)
            assert d is not None
            return d

        return await self._execute(_insert, operation_name="create_backup")

    async def async_get_backup(self, backup_id: int) -> dict[str, Any] | None:
        """Return a single backup by ID."""

        def _query() -> dict[str, Any] | None:
            try:
                backup = UserBackup.get_by_id(backup_id)
            except UserBackup.DoesNotExist:
                return None
            return model_to_dict(backup)

        return await self._execute(_query, operation_name="get_backup", read_only=True)

    async def async_list_backups(self, user_id: int) -> list[dict[str, Any]]:
        """List all backups for a user, ordered by created_at DESC."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                UserBackup.select()
                .where(UserBackup.user == user_id)
                .order_by(UserBackup.created_at.desc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="list_backups", read_only=True)

    async def async_update_backup(self, backup_id: int, **fields: Any) -> None:
        """Update provided fields on a backup record."""

        def _update() -> None:
            backup = UserBackup.get_by_id(backup_id)
            for key, value in fields.items():
                setattr(backup, key, value)
            backup.save()

        await self._execute(_update, operation_name="update_backup")

    async def async_delete_backup(self, backup_id: int) -> None:
        """Hard-delete a backup record."""

        def _delete() -> None:
            UserBackup.delete().where(UserBackup.id == backup_id).execute()

        await self._execute(_delete, operation_name="delete_backup")

    async def async_count_recent_backups(
        self,
        user_id: int,
        since_hours: int = 1,
    ) -> int:
        """Count backups created by user within the last N hours."""
        import datetime as _dt

        from app.core.time_utils import UTC

        since = _dt.datetime.now(UTC) - _dt.timedelta(hours=since_hours)

        def _count() -> int:
            return (
                UserBackup.select()
                .where((UserBackup.user == user_id) & (UserBackup.created_at >= since))
                .count()
            )

        return await self._execute(_count, operation_name="count_recent_backups", read_only=True)
