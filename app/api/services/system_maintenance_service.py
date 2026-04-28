"""Service layer for system maintenance operations."""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import peewee

from app.api.exceptions import ProcessingError, ResourceNotFoundError
from app.config import Config
from app.config.settings import load_config
from app.core.logging_utils import get_logger
from app.db.model_registry import ALL_MODELS
from app.infrastructure.cache.redis_cache import RedisCache

logger = get_logger(__name__)


def _is_safe_sqlite_identifier(identifier: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier))


_DB_INFO_TABLE_ALLOWLIST: frozenset[str] = frozenset(
    model._meta.table_name
    for model in ALL_MODELS
    if _is_safe_sqlite_identifier(model._meta.table_name)
)
_DB_INFO_MODELS_BY_TABLE = {
    model._meta.table_name: model
    for model in ALL_MODELS
    if model._meta.table_name in _DB_INFO_TABLE_ALLOWLIST
}


@dataclass(frozen=True)
class DatabaseDumpFile:
    """Metadata for a generated SQLite backup file."""

    path: str
    filename: str
    media_type: str = "application/x-sqlite3"


class SystemMaintenanceService:
    """Orchestrates DB/Redis maintenance tasks for API endpoints."""

    _CACHE_STALE_SECONDS = 60

    def __init__(
        self,
        *,
        db_path: str | None = None,
        backup_dir: str | None = None,
        backup_filename: str = "ratatoskr_backup.sqlite",
    ) -> None:
        self._db_path = db_path or Config.get("DB_PATH", "/data/app.db")
        self._backup_dir = backup_dir or tempfile.gettempdir()
        self._backup_filename = backup_filename

    def build_db_dump_file(
        self,
        *,
        request_headers: Any,
        user_id: int,
    ) -> DatabaseDumpFile:
        """Create/reuse a DB backup and return file metadata for download."""
        if not os.path.exists(self._db_path):
            raise ResourceNotFoundError("Database file", self._db_path)

        backup_path = os.path.join(self._backup_dir, self._backup_filename)

        if self._should_regenerate_backup(request_headers=request_headers, backup_path=backup_path):
            self._create_backup(backup_path=backup_path, user_id=user_id)

        if not os.path.exists(backup_path):
            raise ResourceNotFoundError("Backup file", backup_path)

        mtime = os.path.getmtime(backup_path)
        timestamp = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y%m%d_%H%M%S")
        download_filename = f"ratatoskr_backup_{timestamp}.sqlite"

        return DatabaseDumpFile(path=backup_path, filename=download_filename)

    def get_db_info(self) -> dict[str, object]:
        """Return DB file metadata and allowlisted table row counts."""
        file_size_mb = 0.0
        if os.path.exists(self._db_path):
            file_size_mb = round(os.path.getsize(self._db_path) / (1024 * 1024), 1)

        table_counts: dict[str, int] = {}

        try:
            allowlisted_tables: list[str] = []
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]

            for table in sorted(tables):
                if not _is_safe_sqlite_identifier(table):
                    table_counts[table] = -1
                    logger.warning("db_info_unsafe_table_name_skipped", extra={"table": table})
                    continue
                if table not in _DB_INFO_TABLE_ALLOWLIST:
                    logger.warning(
                        "db_info_unallowlisted_table_name_skipped", extra={"table": table}
                    )
                    continue
                allowlisted_tables.append(table)

            for table in allowlisted_tables:
                model = _DB_INFO_MODELS_BY_TABLE.get(table)
                if model is None:
                    table_counts[table] = -1
                    logger.warning("db_info_table_model_missing", extra={"table": table})
                    continue
                try:
                    table_counts[table] = int(model.select().count())
                except peewee.DatabaseError as table_exc:
                    table_counts[table] = -1
                    logger.warning(
                        "db_info_table_count_failed",
                        extra={"table": table, "error": str(table_exc)},
                    )
        except sqlite3.Error as exc:
            logger.error("db_info_failed", extra={"error": str(exc)})
            table_counts["__error__"] = -1

        return {
            "file_size_mb": file_size_mb,
            "table_counts": table_counts,
            "db_path": self._db_path,
        }

    async def clear_url_cache(self) -> int:
        """Clear URL cache entries from Redis."""
        cfg = load_config(allow_stub_telegram=True)
        cache = RedisCache(cfg)

        try:
            return await cache.clear_prefix("url")
        except Exception as exc:
            logger.error("clear_cache_failed", extra={"error": str(exc)})
            raise ProcessingError(f"Cache clear failed: {exc}") from exc

    def _should_regenerate_backup(
        self,
        *,
        request_headers: Any,
        backup_path: str,
    ) -> bool:
        lower_headers = {name.lower() for name in request_headers}
        if {"range", "if-match", "if-unmodified-since"} & lower_headers:
            return False

        if not os.path.exists(backup_path):
            return True

        try:
            mtime = os.path.getmtime(backup_path)
        except OSError:
            return True

        return (time.time() - mtime) >= self._CACHE_STALE_SECONDS

    def _create_backup(self, *, backup_path: str, user_id: int) -> None:
        temp_backup_path = backup_path + ".tmp"

        try:
            if os.path.exists(temp_backup_path):
                os.remove(temp_backup_path)

            with (
                sqlite3.connect(self._db_path) as source_conn,
                sqlite3.connect(temp_backup_path) as backup_conn,
            ):
                source_conn.backup(backup_conn)

            os.replace(temp_backup_path, backup_path)
            logger.info(
                "database_backup_created_for_api",
                extra={"backup_path": backup_path, "user_id": user_id},
            )
        except (sqlite3.Error, OSError) as exc:
            cleanup_error: str | None = None

            if os.path.exists(temp_backup_path):
                try:
                    os.remove(temp_backup_path)
                except OSError as cleanup_exc:
                    cleanup_error = str(cleanup_exc)
                    logger.debug("temp_backup_cleanup_failed", extra={"error": cleanup_error})

            details = f"Backup failed: {exc!s}"
            if cleanup_error:
                details += f" (temporary file cleanup also failed: {cleanup_error})"
            raise ProcessingError(details) from exc
