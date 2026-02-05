"""Bootstrap helpers for gRPC server runtime dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger
from app.db.session import DatabaseSessionManager

if TYPE_CHECKING:
    from app.config import AppConfig

logger = get_logger(__name__)


def create_database(cfg: AppConfig) -> DatabaseSessionManager:
    """Create and connect a DatabaseSessionManager based on application config."""
    db = DatabaseSessionManager(
        path=cfg.runtime.db_path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )
    db.database.connect(reuse_if_open=True)
    logger.info("database_initialized", extra={"db_path": cfg.runtime.db_path})
    return db
