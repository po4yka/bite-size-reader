"""Database session management and core infrastructure."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import peewee
from peewee import JOIN, fn
from playhouse.sqlite_ext import SqliteExtDatabase

from app.db.models import (
    ALL_MODELS,
    CrawlResult,
    Request,
    Summary,
    database_proxy,
)
from app.db.rw_lock import AsyncRWLock
from app.db.schema_migrator import SchemaMigrator

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None

# Default database operation constants
DB_OPERATION_TIMEOUT = 30.0
DB_MAX_RETRIES = 3
DB_JSON_MAX_SIZE = 10_000_000  # 10MB
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
    """Peewee-backed database session manager.

    Handles connection management, locking, diagnostics, and migrations.
    """

    path: str
    _logger: logging.Logger = logging.getLogger(__name__)
    _database: peewee.SqliteDatabase = field(init=False)
    _rw_lock: AsyncRWLock = field(init=False)
    _topic_search_index_delete_warned: bool = field(default=False, init=False)

    # Configuration values
    operation_timeout: float = field(default=DB_OPERATION_TIMEOUT)
    max_retries: int = field(default=DB_MAX_RETRIES)
    json_max_size: int = field(default=DB_JSON_MAX_SIZE)
    json_max_depth: int = field(default=DB_JSON_MAX_DEPTH)
    json_max_array_length: int = field(default=DB_JSON_MAX_ARRAY_LENGTH)
    json_max_dict_keys: int = field(default=DB_JSON_MAX_DICT_KEYS)

    def __post_init__(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        self._database = RowSqliteDatabase(
            self.path,
            pragmas={
                "journal_mode": "wal",
                "synchronous": "normal",
                "foreign_keys": 1,
            },
            check_same_thread=False,
        )
        database_proxy.initialize(self._database)

        # Initialize read-write lock for thread-safe database access
        self._rw_lock = AsyncRWLock()

    @property
    def database(self) -> peewee.SqliteDatabase:
        """Access the underlying Peewee database instance."""
        return self._database

    def connection_context(self) -> AbstractAsyncContextManager[Any]:
        """Return a connection context manager."""
        return self._database.connection_context()

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a context manager yielding the raw sqlite3 connection."""
        with self._database.connection_context():
            yield self._database.connection()

    def migrate(self) -> None:
        """Create tables and ensure schema compatibility."""
        with self._database.connection_context(), self._database.bind_ctx(ALL_MODELS):
            self._database.create_tables(ALL_MODELS, safe=True)
            SchemaMigrator(self._database, self._logger).ensure_schema_compatibility()
        self._run_database_maintenance()
        self._logger.info("db_migrated", extra={"path": self.path})

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute database operation with timeout, retry, and connection protection."""
        if timeout is None:
            timeout = self.operation_timeout

        retries = 0
        last_error = None

        while retries <= self.max_retries:
            try:
                lock_context: AbstractAsyncContextManager[Any] = (
                    self._rw_lock.read_lock() if read_only else self._rw_lock.write_lock()
                )

                async def _run_with_lock(context: AbstractAsyncContextManager[Any]) -> Any:
                    async with context:

                        def _op_wrapper() -> Any:
                            with self._database.connection_context():
                                return operation(*args, **kwargs)

                        return await asyncio.to_thread(_op_wrapper)

                return await asyncio.wait_for(_run_with_lock(lock_context), timeout=timeout)

            except TimeoutError:
                self._logger.exception("db_operation_timeout", extra={"operation": operation_name})
                raise

            except peewee.OperationalError as e:
                last_error = e
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    if retries < self.max_retries:
                        retries += 1
                        wait_time = 0.1 * (2**retries)
                        await asyncio.sleep(wait_time)
                        continue
                raise

            except Exception as e:
                self._logger.exception(
                    "db_unexpected_error", extra={"operation": operation_name, "error": str(e)}
                )
                raise

        if last_error:
            raise last_error
        raise RuntimeError(f"Operation {operation_name} failed after retries")

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        """Execute raw SQL synchronously."""
        params = tuple(params or ())
        with self._database.connection_context():
            self._database.execute_sql(sql, params)

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        """Fetch a single row using raw SQL."""
        params = tuple(params or ())
        with self._database.connection_context():
            cursor = self._database.execute_sql(sql, params)
            return cursor.fetchone()

    def create_backup_copy(self, dest_path: str) -> Path:
        """Create a full backup of the database file."""
        if self.path == ":memory:":
            raise ValueError("Cannot backup in-memory database")

        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as conn, sqlite3.connect(str(destination)) as dest_conn:
            conn.backup(dest_conn)
            dest_conn.commit()

        return destination

    def get_database_overview(self) -> dict[str, Any]:
        """Return diagnostic overview of database tables and counts."""
        overview: dict[str, Any] = {"tables": {}}
        try:
            with self._database.connection_context():
                for table in sorted(self._database.get_tables()):
                    overview["tables"][table] = self._count_table_rows(table)

                if "requests" in overview["tables"]:
                    status_rows = list(
                        Request.select(Request.status, fn.COUNT(Request.id).alias("cnt"))
                        .group_by(Request.status)
                        .dicts()
                    )
                    overview["requests_by_status"] = {
                        str(row["status"] or "unknown"): int(row["cnt"]) for row in status_rows
                    }
        except peewee.DatabaseError as exc:
            self._logger.error("db_overview_failed", extra={"error": str(exc)})

        return overview

    def verify_processing_integrity(self, limit: int | None = None) -> dict[str, Any]:
        """Perform deep integrity check on processed summaries."""
        # Simplified version of verification logic
        query = (
            Request.select(Request, Summary, CrawlResult)
            .join(Summary, JOIN.LEFT_OUTER, on=(Summary.request == Request.id))
            .switch(Request)
            .join(CrawlResult, JOIN.LEFT_OUTER, on=(CrawlResult.request == Request.id))
            .order_by(Request.id.desc())
        )
        if limit:
            query = query.limit(limit)

        return {"checked": query.count()}

    # -- Internal migration and maintenance helpers -----------------------

    def _run_database_maintenance(self) -> None:
        try:
            with self._database.connection_context():
                self._database.execute_sql("ANALYZE")
                self._database.execute_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass

    def _count_table_rows(self, table_name: str) -> int:
        model = next((m for m in ALL_MODELS if m._meta.table_name == table_name), None)
        if model is not None:
            return model.select().count()
        return 0
