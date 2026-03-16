from __future__ import annotations

import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import peewee

from app.config import DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.session import DatabaseSessionManager

if TYPE_CHECKING:
    from app.config import AppConfig

logger = get_logger(__name__)

_cached_runtime_db: DatabaseSessionManager | None = None
_cached_runtime_db_lock = threading.Lock()


def build_runtime_database(
    cfg: AppConfig,
    *,
    connect: bool = False,
    migrate: bool = False,
    self_heal: bool = False,
) -> DatabaseSessionManager:
    """Create a runtime database session manager from application config."""
    db = DatabaseSessionManager(
        path=cfg.runtime.db_path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )
    if connect:
        db.database.connect(reuse_if_open=True)
    if migrate:
        if self_heal:
            migrate_with_self_heal(db)
        else:
            db.migrate()
    return db


def get_or_create_runtime_database_from_env(
    *,
    connect: bool = False,
    migrate: bool = True,
) -> DatabaseSessionManager:
    """Lazily build the shared API database outside FastAPI lifespan when needed."""
    global _cached_runtime_db
    if _cached_runtime_db is not None:
        if connect:
            _cached_runtime_db.database.connect(reuse_if_open=True)
        return _cached_runtime_db

    with _cached_runtime_db_lock:
        if _cached_runtime_db is not None:
            if connect:
                _cached_runtime_db.database.connect(reuse_if_open=True)
            return _cached_runtime_db

        db_path = os.getenv("DB_PATH", "/data/app.db")
        db_cfg = _get_env_db_config()
        _cached_runtime_db = DatabaseSessionManager(
            path=db_path,
            operation_timeout=db_cfg.operation_timeout,
            max_retries=db_cfg.max_retries,
            json_max_size=db_cfg.json_max_size,
            json_max_depth=db_cfg.json_max_depth,
            json_max_array_length=db_cfg.json_max_array_length,
            json_max_dict_keys=db_cfg.json_max_dict_keys,
        )
        if migrate:
            _cached_runtime_db.migrate()
        if connect:
            _cached_runtime_db.database.connect(reuse_if_open=True)
        logger.info("runtime_database_initialized", extra={"db_path": db_path})
        return _cached_runtime_db


def clear_cached_runtime_database() -> None:
    """Reset the fallback runtime DB cache used outside managed lifespans."""
    global _cached_runtime_db
    if _cached_runtime_db is not None:
        database = getattr(_cached_runtime_db, "database", None)
        if database is not None:
            database.close()
    _cached_runtime_db = None
    cache_clear = getattr(_get_env_db_config, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


def migrate_with_self_heal(db: DatabaseSessionManager) -> None:
    """Run migrations with one REINDEX-based recovery attempt."""
    try:
        db.migrate()
        return
    except (peewee.OperationalError, sqlite3.OperationalError) as first_err:
        logger.warning(
            "db_migrate_failed",
            extra={"error": str(first_err), "error_type": type(first_err).__name__},
        )

    try:
        with db.connect() as conn:
            cursor = conn.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            integrity_result = result[0] if result else "unknown"
    except Exception as diag_err:
        logger.error("db_integrity_check_failed", extra={"error": str(diag_err)})
        raise

    logger.warning("db_integrity_check_result", extra={"result": integrity_result})
    if integrity_result != "ok":
        logger.warning("db_reindex_starting")
        with db.connect() as conn:
            conn.execute("REINDEX")
        logger.info("db_reindex_completed")

    db.migrate()
    logger.info("db_migrate_retry_succeeded")


def sqlite_read_only_uri(path: str) -> str:
    """Build a file URI that forces SQLite read-only mode."""
    resolved = Path(path).expanduser().resolve()
    return f"{resolved.as_uri()}?mode=ro"


def init_read_only_database_proxy(path: str) -> Any:
    """Bind the Peewee proxy to a read-only SQLite database handle."""
    import peewee

    from app.db.models import database_proxy

    sqlite_uri = sqlite_read_only_uri(path)
    db = peewee.SqliteDatabase(
        sqlite_uri,
        uri=True,
        pragmas={"foreign_keys": 1, "busy_timeout": 5000},
    )
    database_proxy.initialize(db)
    db.connect(reuse_if_open=True)
    logger.info("runtime_database_connected_read_only", extra={"db_path": path})
    return db


@lru_cache(maxsize=1)
def _get_env_db_config() -> DatabaseConfig:
    overrides: dict[str, str] = {
        key: value
        for key, value in {
            "DB_OPERATION_TIMEOUT": os.getenv("DB_OPERATION_TIMEOUT"),
            "DB_MAX_RETRIES": os.getenv("DB_MAX_RETRIES"),
            "DB_JSON_MAX_SIZE": os.getenv("DB_JSON_MAX_SIZE"),
            "DB_JSON_MAX_DEPTH": os.getenv("DB_JSON_MAX_DEPTH"),
            "DB_JSON_MAX_ARRAY_LENGTH": os.getenv("DB_JSON_MAX_ARRAY_LENGTH"),
            "DB_JSON_MAX_DICT_KEYS": os.getenv("DB_JSON_MAX_DICT_KEYS"),
        }.items()
        if value not in (None, "")
    }
    return DatabaseConfig.model_validate(overrides)
