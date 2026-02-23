"""Backward-compatible database facade.

**Deprecated** -- prefer ``DatabaseSessionManager`` + repository adapters for
new code.  This module is retained solely so that existing call-sites and tests
continue to work without modification.

Migration path
--------------
1. ``DatabaseSessionManager``  (``app.db.session``)   -- connections, locks,
   migrations, backup, raw SQL.
2. Repository adapters (``app.infrastructure.persistence.sqlite.repositories``)
   -- per-entity async CRUD.

This facade creates a ``DatabaseSessionManager`` internally and delegates all
infrastructure work to it.  Sync ORM helpers are kept as thin wrappers for
backward compatibility.
"""

from __future__ import annotations

import contextlib
import logging
import warnings
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.db.database_diagnostics import DatabaseDiagnostics
from app.db.database_embedding_media_ops import DatabaseEmbeddingMediaOpsMixin
from app.db.database_maintenance import DatabaseMaintenance
from app.db.database_request_ops import DatabaseRequestOpsMixin
from app.db.database_summary_ops import DatabaseSummaryOpsMixin
from app.db.database_user_ops import DatabaseUserOpsMixin
from app.db.json_utils import (
    decode_json_field,
    normalize_json_container,
    normalize_legacy_json_value,
    prepare_json_payload,
)
from app.db.models import ALL_MODELS
from app.db.session import DatabaseSessionManager
from app.db.topic_search_index import TopicSearchIndexManager
from app.db.video_downloads import VideoDownloadManager
from app.services.topic_search_utils import (
    summary_matches_topic,
    yield_topic_fragments,
)

if TYPE_CHECKING:
    import sqlite3

    import peewee

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None

# Default database operation timeout in seconds
# Prevents indefinite hangs on lock acquisition or slow operations
# Can be overridden via DB_OPERATION_TIMEOUT environment variable
DB_OPERATION_TIMEOUT = 30.0

# Default maximum retries for transient database errors
# Can be overridden via DB_MAX_RETRIES environment variable
DB_MAX_RETRIES = 3

# Default JSON validation limits
# Can be overridden via DB_JSON_* environment variables
DB_JSON_MAX_SIZE = 10_000_000  # 10MB
DB_JSON_MAX_DEPTH = 20
DB_JSON_MAX_ARRAY_LENGTH = 10_000
DB_JSON_MAX_DICT_KEYS = 1_000


@dataclass
class Database(
    DatabaseUserOpsMixin,
    DatabaseRequestOpsMixin,
    DatabaseSummaryOpsMixin,
    DatabaseEmbeddingMediaOpsMixin,
):
    """Peewee-backed database facade providing backward-compatible access.

    .. deprecated::
        Use ``DatabaseSessionManager`` + repository adapters instead.

    This class creates a ``DatabaseSessionManager`` internally and delegates
    infrastructure operations to it while keeping sync ORM helpers for
    backward compatibility with existing tests and call-sites.
    """

    path: str
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    # Managed by __post_init__ -- not user-supplied
    _mgr: DatabaseSessionManager = field(init=False, repr=False)
    _database: peewee.SqliteDatabase = field(init=False, repr=False)
    _diagnostics: DatabaseDiagnostics = field(init=False, repr=False)
    _maintenance: DatabaseMaintenance = field(init=False, repr=False)
    _topic_search: TopicSearchIndexManager = field(init=False, repr=False)
    _video_downloads: VideoDownloadManager = field(init=False, repr=False)

    # Configuration values (can be set via database_config parameter or use module defaults)
    operation_timeout: float = field(default=DB_OPERATION_TIMEOUT)
    max_retries: int = field(default=DB_MAX_RETRIES)
    json_max_size: int = field(default=DB_JSON_MAX_SIZE)
    json_max_depth: int = field(default=DB_JSON_MAX_DEPTH)
    json_max_array_length: int = field(default=DB_JSON_MAX_ARRAY_LENGTH)
    json_max_dict_keys: int = field(default=DB_JSON_MAX_DICT_KEYS)

    def __post_init__(self) -> None:
        warnings.warn(
            "Database is deprecated; use DatabaseSessionManager + repository adapters",
            DeprecationWarning,
            stacklevel=2,
        )
        self._mgr = DatabaseSessionManager(
            path=self.path,
            _logger=self._logger,
            operation_timeout=self.operation_timeout,
            max_retries=self.max_retries,
            json_max_size=self.json_max_size,
            json_max_depth=self.json_max_depth,
            json_max_array_length=self.json_max_array_length,
            json_max_dict_keys=self.json_max_dict_keys,
        )
        self._database = self._mgr.database
        self._diagnostics = DatabaseDiagnostics(self._database, self._logger)
        self._maintenance = DatabaseMaintenance(self._database, self.path, self._logger)
        self._topic_search = TopicSearchIndexManager(self._database, self._logger)
        self._video_downloads = VideoDownloadManager(self._logger)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def database(self) -> peewee.SqliteDatabase:
        """Access the underlying Peewee database instance."""
        return self._database

    # ------------------------------------------------------------------
    # Infrastructure -- delegated to DatabaseSessionManager
    # ------------------------------------------------------------------

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute database operation with timeout and retry protection."""
        return await self._mgr._safe_db_operation(
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
        """Execute database operation within an explicit transaction."""
        return await self._mgr._safe_db_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a context manager yielding the raw sqlite3 connection."""
        with self._mgr.connect() as conn:
            yield conn

    def migrate(self) -> None:
        """Create tables, run migrations, and perform startup maintenance."""
        with self._database.connection_context(), self._database.bind_ctx(ALL_MODELS):
            self._database.create_tables(ALL_MODELS, safe=True)

            from app.cli.migrations.migration_runner import MigrationRunner

            runner = MigrationRunner(self)
            runner.run_pending()

            from app.db.schema_migrator import SchemaMigrator

            SchemaMigrator(self._database, self._logger).ensure_schema_compatibility()

            self._topic_search.ensure_index()

        self._run_database_maintenance()
        self._logger.info("db_migrated", extra={"path": self.path})

    def create_backup_copy(self, dest_path: str) -> Path:
        """Create a full backup of the database file."""
        return self._mgr.create_backup_copy(dest_path)

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        """Execute raw SQL synchronously."""
        self._mgr.execute(sql, params)

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        """Fetch a single row using raw SQL."""
        return self._mgr.fetchone(sql, params)

    # ------------------------------------------------------------------
    # JSON utilities -- static delegates kept for backward compat
    # ------------------------------------------------------------------

    _normalize_json_container = staticmethod(normalize_json_container)
    _prepare_json_payload = staticmethod(prepare_json_payload)
    _normalize_legacy_json_value = staticmethod(normalize_legacy_json_value)

    def _decode_json_field(self, value: Any) -> tuple[Any | None, str | None]:
        """Decode JSON field with security validation."""
        return decode_json_field(
            value,
            max_size=self.json_max_size,
            max_depth=self.json_max_depth,
            max_array_length=self.json_max_array_length,
            max_dict_keys=self.json_max_dict_keys,
        )

    # ------------------------------------------------------------------
    # Diagnostics / maintenance delegates
    # ------------------------------------------------------------------

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

    def _run_database_maintenance(self) -> None:
        """Run database maintenance operations (ANALYZE, VACUUM)."""
        self._maintenance.run_maintenance()

    def _run_analyze(self) -> None:
        """Run ANALYZE to update query planner statistics."""
        self._maintenance.run_analyze()

    def _run_vacuum(self) -> None:
        """Run VACUUM to reclaim disk space and defragment."""
        self._maintenance.run_vacuum()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mask_path(self, path: str) -> str:
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

    @staticmethod
    def _convert_bool_fields(data: dict[str, Any], fields: Iterable[str]) -> None:
        for field_name in fields:
            if field_name in data and data[field_name] is not None:
                data[field_name] = int(bool(data[field_name]))

    _yield_topic_fragments = staticmethod(yield_topic_fragments)
    _summary_matches_topic = staticmethod(summary_matches_topic)
