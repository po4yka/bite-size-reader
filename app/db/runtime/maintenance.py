"""Database maintenance service."""

from __future__ import annotations

from typing import Any

from app.db.database_maintenance import DatabaseMaintenance


class DatabaseMaintenanceService:
    """Run periodic and startup database maintenance operations."""

    def __init__(self, *, database: Any, path: str, logger: Any) -> None:
        self._maintenance = DatabaseMaintenance(database, path, logger)

    def run_startup_maintenance(self) -> None:
        """Run the low-cost startup maintenance path used by the runtime."""
        if self._maintenance._path == ":memory:":
            self._maintenance._logger.debug("db_maintenance_skipped_in_memory")
            return
        self._maintenance.run_analyze()
        self._maintenance.run_wal_checkpoint(mode="TRUNCATE")

    def run_maintenance(self) -> dict[str, Any]:
        return self._maintenance.run_maintenance()

    def run_analyze(self) -> bool:
        return self._maintenance.run_analyze()

    def run_vacuum(self) -> bool:
        return self._maintenance.run_vacuum()

    def run_wal_checkpoint(self, mode: str = "TRUNCATE") -> bool:
        return self._maintenance.run_wal_checkpoint(mode=mode)

    def get_database_stats(self) -> dict[str, Any]:
        return self._maintenance.get_database_stats()
