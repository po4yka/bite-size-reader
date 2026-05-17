"""Database dependency wiring."""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.session import Database

if TYPE_CHECKING:
    from app.config import AppConfig

logger = get_logger(__name__)

_cached_runtime_db_holder: list[Database | None] = [None]
_cached_runtime_db_lock = threading.Lock()


def build_runtime_database(
    cfg: AppConfig,
    *,
    connect: bool = False,
    migrate: bool = False,
    self_heal: bool = False,
) -> Database:
    """Create the runtime SQLAlchemy database facade from application config."""
    del self_heal
    db = Database(config=cfg.database)
    if connect:
        asyncio.run(db.healthcheck())
    if migrate:
        asyncio.run(db.migrate())
    return db


def get_or_create_runtime_database_from_env(
    *,
    connect: bool = False,
    migrate: bool = True,
) -> Database:
    """Lazily build the shared API database outside FastAPI lifespan when needed."""
    cached = _cached_runtime_db_holder[0]
    if cached is not None:
        if connect:
            asyncio.run(cached.healthcheck())
        return cached

    with _cached_runtime_db_lock:
        cached = _cached_runtime_db_holder[0]
        if cached is not None:
            if connect:
                asyncio.run(cached.healthcheck())
            return cached

        db = Database(config=_get_env_db_config())
        if migrate:
            asyncio.run(db.migrate())
        if connect:
            asyncio.run(db.healthcheck())
        _cached_runtime_db_holder[0] = db
        logger.info("runtime_database_initialized")
        return db


def clear_cached_runtime_database() -> None:
    """Reset the fallback runtime DB cache used outside managed lifespans."""
    cached = _cached_runtime_db_holder[0]
    if cached is not None:
        asyncio.run(cached.dispose())
    _cached_runtime_db_holder[0] = None
    cache_clear = getattr(_get_env_db_config, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


@lru_cache(maxsize=1)
def _get_env_db_config() -> DatabaseConfig:
    return DatabaseConfig()
