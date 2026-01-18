"""Database session management dependency for FastAPI."""

from __future__ import annotations

import os
from functools import lru_cache

from app.config import Config, DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_session_manager: DatabaseSessionManager | None = None


def get_session_manager() -> DatabaseSessionManager:
    """Get the global database session manager.

    This is lazily initialized on first call and reused thereafter.
    The session manager handles connection pooling, locking, and migrations.

    Returns:
        DatabaseSessionManager: The global database session manager instance.
    """
    global _session_manager

    if _session_manager is not None:
        return _session_manager

    db_path = Config.get("DB_PATH", "/data/app.db")
    db_cfg = _get_db_config()

    _session_manager = DatabaseSessionManager(
        path=db_path,
        operation_timeout=db_cfg.operation_timeout,
        max_retries=db_cfg.max_retries,
        json_max_size=db_cfg.json_max_size,
        json_max_depth=db_cfg.json_max_depth,
        json_max_array_length=db_cfg.json_max_array_length,
        json_max_dict_keys=db_cfg.json_max_dict_keys,
    )

    logger.info("session_manager_initialized", extra={"db_path": db_path})
    return _session_manager


@lru_cache(maxsize=1)
def _get_db_config() -> DatabaseConfig:
    """Get database configuration from environment."""
    return DatabaseConfig(
        **{
            key: value
            for key, value in {
                "operation_timeout": os.getenv("DB_OPERATION_TIMEOUT"),
                "max_retries": os.getenv("DB_MAX_RETRIES"),
                "json_max_size": os.getenv("DB_JSON_MAX_SIZE"),
                "json_max_depth": os.getenv("DB_JSON_MAX_DEPTH"),
                "json_max_array_length": os.getenv("DB_JSON_MAX_ARRAY_LENGTH"),
                "json_max_dict_keys": os.getenv("DB_JSON_MAX_DICT_KEYS"),
            }.items()
            if value not in (None, "")
        }
    )
