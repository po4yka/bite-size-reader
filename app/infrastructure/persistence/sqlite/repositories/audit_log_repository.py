"""SQLite implementation of audit log repository.

This adapter handles persistence for application audit events and security logs.
"""

from __future__ import annotations

from typing import Any

from app.db.models import AuditLog
from app.db.utils import prepare_json_payload
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteAuditLogRepositoryAdapter(SqliteBaseRepository):
    """Adapter for audit logging operations."""

    async def async_insert_audit_log(
        self,
        log_level: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Insert a new audit log record."""

        def _insert() -> int:
            log = AuditLog.create(
                level=log_level,
                event=event_type,
                details_json=prepare_json_payload(details),
            )
            return log.id

        return await self._execute(_insert, operation_name="insert_audit_log")
