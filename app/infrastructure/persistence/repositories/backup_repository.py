"""SQLAlchemy implementation of the backup repository."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update

from app.core.time_utils import UTC
from app.db.models import UserBackup, model_to_dict
from app.db.types import _utcnow

if TYPE_CHECKING:
    from app.db.session import Database


class BackupRepositoryAdapter:
    """Adapter for user backup CRUD operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_create_backup(
        self,
        user_id: int,
        type: str = "manual",
    ) -> dict[str, Any]:
        """Create a new backup record and return it as a dict."""
        async with self._database.transaction() as session:
            backup = UserBackup(user_id=user_id, type=type, status="pending")
            session.add(backup)
            await session.flush()
            return model_to_dict(backup) or {}

    async def async_get_backup(self, backup_id: int) -> dict[str, Any] | None:
        """Return a single backup by ID."""
        async with self._database.session() as session:
            backup = await session.get(UserBackup, backup_id)
            return model_to_dict(backup)

    async def async_list_backups(self, user_id: int) -> list[dict[str, Any]]:
        """List all backups for a user, ordered by created_at DESC."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(UserBackup)
                    .where(UserBackup.user_id == user_id)
                    .order_by(UserBackup.created_at.desc())
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def async_update_backup(self, backup_id: int, **fields: Any) -> None:
        """Update provided fields on a backup record."""
        if not fields:
            return
        allowed_fields = set(UserBackup.__mapper__.columns.keys()) - {"id"}
        update_values = {key: value for key, value in fields.items() if key in allowed_fields}
        if not update_values:
            return
        update_values["updated_at"] = _utcnow()
        async with self._database.transaction() as session:
            await session.execute(
                update(UserBackup).where(UserBackup.id == backup_id).values(**update_values)
            )

    async def async_delete_backup(self, backup_id: int) -> None:
        """Hard-delete a backup record."""
        async with self._database.transaction() as session:
            await session.execute(delete(UserBackup).where(UserBackup.id == backup_id))

    async def async_count_recent_backups(
        self,
        user_id: int,
        since_hours: int = 1,
    ) -> int:
        """Count backups created by user within the last N hours."""
        since = dt.datetime.now(UTC) - dt.timedelta(hours=since_hours)
        async with self._database.session() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(UserBackup)
                    .where(UserBackup.user_id == user_id, UserBackup.created_at >= since)
                )
                or 0
            )
