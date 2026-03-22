"""Backup ports."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BackupRepositoryPort(Protocol):
    """Port for user backup archive operations."""

    async def async_create_backup(
        self, user_id: int, backup_type: str = "manual"
    ) -> dict[str, Any]:
        """Insert a new UserBackup and return the created record."""

    async def async_get_backup(self, backup_id: int) -> dict[str, Any] | None:
        """Return a single backup by ID."""

    async def async_list_backups(self, user_id: int) -> list[dict[str, Any]]:
        """List user's backups, ordered by created_at DESC."""

    async def async_update_backup(self, backup_id: int, **fields: Any) -> None:
        """Update provided fields on a backup record."""

    async def async_delete_backup(self, backup_id: int) -> None:
        """Hard delete a backup record."""

    async def async_count_recent_backups(self, user_id: int, since_hours: int = 1) -> int:
        """Count backups created within the last N hours (for rate limiting)."""
