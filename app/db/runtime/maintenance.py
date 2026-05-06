"""Database maintenance service."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class DatabaseMaintenanceService:
    """Run PostgreSQL maintenance operations."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        logger: Any,
    ) -> None:
        self._engine = engine
        self._session_maker = session_maker
        self._logger = logger

    def run_startup_maintenance(self) -> None:
        """Postgres does not need startup PRAGMA/WAL maintenance."""
        self._logger.info("db_startup_maintenance_skipped")

    def run_maintenance(self) -> dict[str, Any]:
        analyze_ok = self.run_analyze()
        return {
            "status": "success" if analyze_ok else "partial",
            "operations": {"analyze": "success" if analyze_ok else "failed"},
        }

    def run_analyze(self) -> bool:
        return _run_sync(self.async_run_analyze())

    async def async_run_analyze(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("ANALYZE"))
                await connection.commit()
            self._logger.debug("db_analyze_completed")
            return True
        except SQLAlchemyError as exc:
            self._logger.warning("db_analyze_failed", extra={"error": str(exc)})
            return False

    def run_vacuum(self) -> bool:
        return _run_sync(self.async_run_vacuum())

    async def async_run_vacuum(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
                await autocommit.execute(text("VACUUM"))
            self._logger.debug("db_vacuum_completed")
            return True
        except SQLAlchemyError as exc:
            self._logger.warning("db_vacuum_failed", extra={"error": str(exc)})
            return False

    def run_wal_checkpoint(self, mode: str = "TRUNCATE") -> bool:
        del mode
        self._logger.info("db_wal_checkpoint_skipped_postgres")
        return True

    def get_database_stats(self) -> dict[str, Any]:
        return _run_sync(self.async_get_database_stats())

    async def async_get_database_stats(self) -> dict[str, Any]:
        async with self._session_maker() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT pg_database_size(current_database()) AS size_bytes, "
                            "xact_commit, xact_rollback "
                            "FROM pg_stat_database "
                            "WHERE datname = current_database()"
                        )
                    )
                )
                .mappings()
                .one()
            )
        size_bytes = int(row["size_bytes"] or 0)
        return {
            "type": "postgres",
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "xact_commit": int(row["xact_commit"] or 0),
            "xact_rollback": int(row["xact_rollback"] or 0),
        }


def _run_sync(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    msg = "Synchronous database maintenance methods cannot run inside an active event loop"
    raise RuntimeError(msg)
