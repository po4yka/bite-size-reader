"""Database session management and core infrastructure.

This module provides the DatabaseSessionManager class, which is the primary
infrastructure component for database operations. It handles:
- Connection management with SQLite
- Read/write locking for concurrent access
- Async operation wrappers with timeout and retry logic
- Database migrations and maintenance
- Backup creation
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
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

    Handles connection management, locking, async operations, and migrations.
    This is the core infrastructure class that repositories use for database access.

    Attributes:
        path: Path to the SQLite database file, or ":memory:" for in-memory
        operation_timeout: Default timeout for database operations in seconds
        max_retries: Maximum retries for transient database errors
        json_max_size: Maximum size for JSON fields in bytes
        json_max_depth: Maximum nesting depth for JSON fields
        json_max_array_length: Maximum array length in JSON fields
        json_max_dict_keys: Maximum dictionary keys in JSON fields
    """

    path: str
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
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

    def connection_context(self) -> Any:
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
        self._logger.info("db_migrated", extra={"path": self._mask_path(self.path)})

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute database operation with timeout, retry, and connection protection.

        Args:
            operation: The database operation to execute
            *args: Positional arguments for the operation
            timeout: Timeout in seconds (default: self.operation_timeout)
            operation_name: Name for logging purposes
            read_only: Whether this is a read-only operation (allows concurrent reads)
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            asyncio.TimeoutError: If operation times out
            peewee.OperationalError: If database is locked or busy after retries
            peewee.IntegrityError: If constraint violation occurs
            Exception: Other database errors
        """
        if timeout is None:
            timeout = self.operation_timeout

        retries = 0
        last_error = None

        while retries <= self.max_retries:
            try:

                async def _run_with_lock() -> Any:
                    def _op_wrapper() -> Any:
                        with self._database.connection_context():
                            return operation(*args, **kwargs)

                    if read_only:
                        # Read operations don't need application-level locking.
                        # SQLite WAL mode (configured in __post_init__) handles
                        # reader-writer coordination at the database level,
                        # allowing concurrent reads with a single writer.
                        return await asyncio.to_thread(_op_wrapper)

                    async with self._rw_lock.write_lock():
                        return await asyncio.to_thread(_op_wrapper)

                return await asyncio.wait_for(_run_with_lock(), timeout=timeout)

            except TimeoutError:
                self._logger.exception(
                    "db_operation_timeout",
                    extra={
                        "operation": operation_name,
                        "timeout": timeout,
                        "retries": retries,
                    },
                )
                raise

            except peewee.OperationalError as e:
                last_error = e
                error_msg = str(e).lower()

                if "locked" in error_msg or "busy" in error_msg:
                    if retries < self.max_retries:
                        retries += 1
                        wait_time = 0.1 * (2**retries)  # Exponential backoff
                        self._logger.warning(
                            "db_locked_retrying",
                            extra={
                                "operation": operation_name,
                                "retry": retries,
                                "max_retries": self.max_retries,
                                "wait_time": wait_time,
                                "error": str(e),
                            },
                        )
                        await asyncio.sleep(wait_time)
                        continue

                self._logger.exception(
                    "db_operational_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                    },
                )
                raise

            except peewee.IntegrityError as e:
                self._logger.exception(
                    "db_integrity_error",
                    extra={
                        "operation": operation_name,
                        "error": str(e),
                    },
                )
                raise

            except Exception as e:
                self._logger.exception(
                    "db_unexpected_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

        if last_error:
            raise last_error
        msg = f"Database operation {operation_name} failed after {self.max_retries} retries"
        raise RuntimeError(msg)

    async def _safe_db_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute database operation within an explicit transaction with rollback.

        This method wraps database operations in an atomic transaction, ensuring
        that all changes are either committed together or rolled back on error.

        Args:
            operation: The database operation to execute
            *args: Positional arguments for the operation
            timeout: Timeout in seconds (default: self.operation_timeout)
            operation_name: Name for logging purposes
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            asyncio.TimeoutError: If operation times out
            peewee.OperationalError: If database is locked or busy after retries
            peewee.IntegrityError: If constraint violation occurs
            Exception: Other database errors
        """
        if timeout is None:
            timeout = self.operation_timeout

        retries = 0
        last_error = None

        while retries <= self.max_retries:
            try:
                # Transactions always require write lock
                async def _run_transaction() -> Any:
                    async with self._rw_lock.write_lock():

                        def _execute_in_transaction() -> Any:
                            with self._database.atomic() as txn:
                                try:
                                    return operation(*args, **kwargs)
                                except BaseException:
                                    txn.rollback()
                                    raise

                        return await asyncio.to_thread(_execute_in_transaction)

                return await asyncio.wait_for(_run_transaction(), timeout=timeout)

            except TimeoutError:
                self._logger.exception(
                    "db_transaction_timeout",
                    extra={
                        "operation": operation_name,
                        "timeout": timeout,
                        "retries": retries,
                    },
                )
                raise

            except peewee.OperationalError as e:
                last_error = e
                error_msg = str(e).lower()

                if "locked" in error_msg or "busy" in error_msg:
                    if retries < self.max_retries:
                        retries += 1
                        wait_time = 0.1 * (2**retries)
                        self._logger.warning(
                            "db_transaction_locked_retrying",
                            extra={
                                "operation": operation_name,
                                "retry": retries,
                                "max_retries": self.max_retries,
                                "wait_time": wait_time,
                                "error": str(e),
                            },
                        )
                        await asyncio.sleep(wait_time)
                        continue

                self._logger.exception(
                    "db_transaction_operational_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                    },
                )
                raise

            except peewee.IntegrityError as e:
                self._logger.exception(
                    "db_transaction_integrity_error",
                    extra={
                        "operation": operation_name,
                        "error": str(e),
                    },
                )
                raise

            except Exception as e:
                self._logger.exception(
                    "db_transaction_unexpected_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

        if last_error:
            raise last_error
        msg = f"Database transaction {operation_name} failed after {self.max_retries} retries"
        raise RuntimeError(msg)

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        """Execute raw SQL synchronously."""
        params = tuple(params or ())
        with self._database.connection_context():
            self._database.execute_sql(sql, params)
        self._logger.debug("db_execute", extra={"sql": sql, "params": list(params)[:10]})

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        """Fetch a single row using raw SQL."""
        params = tuple(params or ())
        with self._database.connection_context():
            cursor = self._database.execute_sql(sql, params)
            return cursor.fetchone()

    def create_backup_copy(self, dest_path: str) -> Path:
        """Create a full backup of the database file.

        Args:
            dest_path: Destination path for the backup

        Returns:
            Path to the created backup file

        Raises:
            ValueError: If trying to backup an in-memory database
            FileNotFoundError: If source database file doesn't exist
        """
        if self.path == ":memory:":
            raise ValueError("Cannot create a backup for an in-memory database")

        source = Path(self.path)
        if not source.exists():
            raise FileNotFoundError(f"Database file not found at {self.path}")

        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as conn, sqlite3.connect(str(destination)) as dest_conn:
            conn.backup(dest_conn)
            dest_conn.commit()

        self._logger.info(
            "db_backup_copy_created",
            extra={
                "source": self._mask_path(str(source)),
                "dest": self._mask_path(str(destination)),
            },
        )
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

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Perform deep integrity check on processed summaries."""
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

    # -- Internal helpers -------------------------------------------------

    @staticmethod
    def _mask_path(path: str) -> str:
        """Mask a path for logging (show only parent/filename)."""
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

    def _run_database_maintenance(self) -> None:
        """Run database maintenance operations (ANALYZE, checkpoint)."""
        if self.path == ":memory:":
            self._logger.debug("db_maintenance_skipped_in_memory")
            return

        try:
            with self._database.connection_context():
                self._database.execute_sql("ANALYZE")
                self._database.execute_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_maintenance_failed",
                extra={"path": self._mask_path(self.path), "error": str(exc)},
            )

    def _count_table_rows(self, table_name: str) -> int:
        """Count rows in a table by model."""
        model = next((m for m in ALL_MODELS if m._meta.table_name == table_name), None)
        if model is not None:
            return model.select().count()
        return 0
