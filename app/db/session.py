"""Database session management and runtime façade."""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from playhouse.sqlite_ext import SqliteExtDatabase

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    import peewee

from app.core.logging_utils import get_logger
from app.db.runtime.backup import DatabaseBackupService
from app.db.runtime.bootstrap import DatabaseBootstrapService
from app.db.runtime.inspection import DatabaseInspectionService
from app.db.runtime.maintenance import DatabaseMaintenanceService
from app.db.runtime.operation_executor import DatabaseOperationExecutor
from app.db.rw_lock import AsyncRWLock

if TYPE_CHECKING:
    import logging

JSONValue = dict[str, Any] | list[Any] | str | None

DB_OPERATION_TIMEOUT = 30.0
DB_MAX_RETRIES = 3
DB_JSON_MAX_SIZE = 10_000_000
DB_JSON_MAX_DEPTH = 20
DB_JSON_MAX_ARRAY_LENGTH = 10_000
DB_JSON_MAX_DICT_KEYS = 1_000


class TopicSearchIndexRebuiltError(RuntimeError):
    """Raised to signal that the topic search index was rebuilt mid-operation."""


class RowSqliteDatabase(SqliteExtDatabase):
    """SQLite database subclass that configures the row factory for dict-like access."""

    def _connect(self) -> sqlite3.Connection:
        conn = super()._connect()
        conn.row_factory = sqlite3.Row
        return conn


@dataclass
class DatabaseSessionManager:
    """Compatibility façade over dedicated database runtime services."""

    path: str
    _logger: logging.Logger = field(default_factory=lambda: get_logger(__name__))
    _database: peewee.SqliteDatabase = field(init=False)
    _rw_lock: AsyncRWLock = field(init=False)

    operation_timeout: float = field(default=DB_OPERATION_TIMEOUT)
    max_retries: int = field(default=DB_MAX_RETRIES)
    json_max_size: int = field(default=DB_JSON_MAX_SIZE)
    json_max_depth: int = field(default=DB_JSON_MAX_DEPTH)
    json_max_array_length: int = field(default=DB_JSON_MAX_ARRAY_LENGTH)
    json_max_dict_keys: int = field(default=DB_JSON_MAX_DICT_KEYS)

    def __post_init__(self) -> None:
        self._database = RowSqliteDatabase(
            self.path,
            pragmas={
                "journal_mode": "wal",
                "synchronous": "normal",
                "foreign_keys": 1,
            },
            check_same_thread=False,
        )
        self._rw_lock = AsyncRWLock()

        self._bootstrap = DatabaseBootstrapService(
            path=self.path,
            database=self._database,
            logger=self._logger,
        )
        self._bootstrap.initialize_database_proxy()
        self._executor = DatabaseOperationExecutor(
            database=self._database,
            rw_lock=self._rw_lock,
            operation_timeout=self.operation_timeout,
            max_retries=self.max_retries,
            logger=self._logger,
        )
        self._maintenance = DatabaseMaintenanceService(
            database=self._database,
            path=self.path,
            logger=self._logger,
        )
        self._inspection = DatabaseInspectionService(
            database=self._database,
            path=self.path,
            logger=self._logger,
        )
        self._backup = DatabaseBackupService(
            path=self.path,
            connect=self.connect,
            logger=self._logger,
        )

    @property
    def database(self) -> peewee.SqliteDatabase:
        return self._database

    @property
    def executor(self) -> DatabaseOperationExecutor:
        return self._executor

    @property
    def bootstrap(self) -> DatabaseBootstrapService:
        return self._bootstrap

    @property
    def maintenance(self) -> DatabaseMaintenanceService:
        return self._maintenance

    @property
    def inspection(self) -> DatabaseInspectionService:
        return self._inspection

    @property
    def backups(self) -> DatabaseBackupService:
        return self._backup

    def connection_context(self) -> Any:
        return self._executor.connection_context()

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._database.connection_context():
            yield self._database.connection()

    def migrate(self) -> None:
        self._bootstrap.migrate()
        self._maintenance.run_startup_maintenance()

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        return await self._executor.async_execute(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            read_only=read_only,
            **kwargs,
        )

    async def _safe_db_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_transaction",
        **kwargs: Any,
    ) -> Any:
        return await self._executor.async_execute_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )

    async def async_execute(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        return await self._executor.async_execute(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            read_only=read_only,
            **kwargs,
        )

    async def async_execute_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "repository_transaction",
        **kwargs: Any,
    ) -> Any:
        return await self._executor.async_execute_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        params = tuple(params or ())
        with self._database.connection_context():
            self._database.execute_sql(sql, params)
        self._logger.debug("db_execute", extra={"sql": sql, "params": list(params)[:10]})

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        params = tuple(params or ())
        with self._database.connection_context():
            cursor = self._database.execute_sql(sql, params)
            return cursor.fetchone()

    def create_backup_copy(self, dest_path: str) -> Path:
        return self._backup.create_backup_copy(dest_path)

    def check_integrity(self) -> tuple[bool, str]:
        return self._inspection.check_integrity()

    def get_database_overview(self) -> dict[str, Any]:
        return self._inspection.get_database_overview()

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._inspection.verify_processing_integrity(
            required_fields=required_fields,
            limit=limit,
        )
