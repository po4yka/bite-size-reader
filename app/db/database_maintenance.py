"""Database maintenance operations.

This module provides utilities for running database maintenance tasks
like ANALYZE and VACUUM to optimize SQLite performance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import peewee

if TYPE_CHECKING:
    from playhouse.sqlite_ext import SqliteExtDatabase


class DatabaseMaintenance:
    """Handles database maintenance operations.

    This class encapsulates maintenance tasks that should be run periodically
    to keep the SQLite database performing optimally.
    """

    def __init__(
        self,
        database: SqliteExtDatabase,
        path: str,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the maintenance handler.

        Args:
            database: The Peewee database instance
            path: Path to the database file
            logger: Optional logger instance
        """
        self._database = database
        self._path = path
        self._logger = logger or logging.getLogger(__name__)

    def run_maintenance(self) -> dict[str, Any]:
        """Run all maintenance operations.

        Returns:
            Dict with status of each operation
        """
        if self._path == ":memory:":
            self._logger.debug("db_maintenance_skipped_in_memory")
            return {"status": "skipped", "reason": "in-memory database"}

        results: dict[str, Any] = {"status": "success", "operations": {}}

        analyze_ok = self.run_analyze()
        results["operations"]["analyze"] = "success" if analyze_ok else "failed"

        vacuum_ok = self.run_vacuum()
        results["operations"]["vacuum"] = "success" if vacuum_ok else "failed"

        if not analyze_ok or not vacuum_ok:
            results["status"] = "partial"

        return results

    def run_analyze(self) -> bool:
        """Run ANALYZE to update query planner statistics.

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._database.connection_context():
                self._database.execute_sql("ANALYZE;")
            self._logger.debug("db_analyze_completed", extra={"path": self._mask_path()})
            return True
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_analyze_failed",
                extra={"path": self._mask_path(), "error": str(exc)},
            )
            return False

    def run_vacuum(self) -> bool:
        """Run VACUUM to reclaim disk space and defragment.

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._database.connection_context():
                self._database.execute_sql("VACUUM;")
            self._logger.debug("db_vacuum_completed", extra={"path": self._mask_path()})
            return True
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_vacuum_failed",
                extra={"path": self._mask_path(), "error": str(exc)},
            )
            return False

    def run_wal_checkpoint(self, mode: str = "TRUNCATE") -> bool:
        """Run WAL checkpoint to sync WAL file to main database.

        Args:
            mode: Checkpoint mode (PASSIVE, FULL, RESTART, or TRUNCATE)

        Returns:
            True if successful, False otherwise
        """
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        if mode.upper() not in valid_modes:
            self._logger.warning(
                "db_wal_checkpoint_invalid_mode",
                extra={"mode": mode, "valid_modes": list(valid_modes)},
            )
            return False

        try:
            with self._database.connection_context():
                self._database.execute_sql(f"PRAGMA wal_checkpoint({mode.upper()});")
            self._logger.debug(
                "db_wal_checkpoint_completed",
                extra={"path": self._mask_path(), "mode": mode},
            )
            return True
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_wal_checkpoint_failed",
                extra={"path": self._mask_path(), "mode": mode, "error": str(exc)},
            )
            return False

    def get_database_stats(self) -> dict[str, Any]:
        """Get database file statistics.

        Returns:
            Dict with file size, WAL size, and other stats
        """
        stats: dict[str, Any] = {}

        if self._path == ":memory:":
            stats["type"] = "in-memory"
            return stats

        db_path = Path(self._path)
        if db_path.exists():
            stats["size_bytes"] = db_path.stat().st_size
            stats["size_mb"] = round(stats["size_bytes"] / (1024 * 1024), 2)

        wal_path = Path(f"{self._path}-wal")
        if wal_path.exists():
            stats["wal_size_bytes"] = wal_path.stat().st_size
            stats["wal_size_mb"] = round(stats["wal_size_bytes"] / (1024 * 1024), 2)

        shm_path = Path(f"{self._path}-shm")
        if shm_path.exists():
            stats["shm_size_bytes"] = shm_path.stat().st_size

        try:
            with self._database.connection_context():
                # Get page count and size
                cursor = self._database.execute_sql("PRAGMA page_count;")
                row = cursor.fetchone()
                if row:
                    stats["page_count"] = row[0]

                cursor = self._database.execute_sql("PRAGMA page_size;")
                row = cursor.fetchone()
                if row:
                    stats["page_size"] = row[0]

                cursor = self._database.execute_sql("PRAGMA freelist_count;")
                row = cursor.fetchone()
                if row:
                    stats["freelist_count"] = row[0]

        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_stats_query_failed",
                extra={"error": str(exc)},
            )

        return stats

    def _mask_path(self) -> str:
        """Mask the database path for logging."""
        try:
            p = Path(self._path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except (OSError, ValueError, AttributeError):
            return "..."
