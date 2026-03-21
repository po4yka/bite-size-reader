"""Database inspection and integrity services."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

import peewee

from app.db.database_diagnostics import DatabaseDiagnostics


class DatabaseInspectionService:
    """Expose database integrity and diagnostics operations."""

    def __init__(self, *, database: peewee.SqliteDatabase, path: str, logger: Any) -> None:
        self._database = database
        self._path = path
        self._logger = logger
        self._diagnostics = DatabaseDiagnostics(database, logger)

    def check_integrity(self) -> tuple[bool, str]:
        try:
            with self._database.connection_context():
                cursor = self._database.execute_sql("PRAGMA quick_check")
                row = cursor.fetchone()
                result = row[0] if row else "unknown"
                is_ok = result == "ok"
                if not is_ok:
                    self._logger.warning(
                        "db_quick_check_issue",
                        extra={"result": result, "path": self._mask_path(self._path)},
                    )
                return is_ok, str(result)
        except (peewee.DatabaseError, sqlite3.DatabaseError) as exc:
            self._logger.error(
                "db_quick_check_failed",
                extra={"error": str(exc), "path": self._mask_path(self._path)},
            )
            return False, str(exc)

    def get_database_overview(self) -> dict[str, Any]:
        return self._diagnostics.get_database_overview()

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._diagnostics.verify_processing_integrity(
            required_fields=required_fields,
            limit=limit,
        )

    @staticmethod
    def _mask_path(path: str) -> str:
        try:
            p = Path(path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except (OSError, ValueError, AttributeError):
            return "..."
