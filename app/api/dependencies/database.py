"""Database session management dependency for FastAPI."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from app.application.use_cases.search_read_model import SearchReadModelUseCase
from app.application.use_cases.summary_read_model import SummaryReadModelUseCase
from app.config import Config, DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.models import database_proxy
from app.db.session import DatabaseSessionManager
from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
    SqliteAuthRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.collection_repository import (
    SqliteCollectionRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.device_repository import (
    SqliteDeviceRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

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
    _session_manager.migrate()

    logger.info("session_manager_initialized", extra={"db_path": db_path})
    return _session_manager


def clear_session_manager() -> None:
    """Reset the cached API session manager.

    Used in tests to avoid leaking a previous database binding across test cases.
    """
    global _session_manager
    if _session_manager is not None:
        _session_manager.database.close()
    _session_manager = None


def resolve_repository_session(
    session_manager: DatabaseSessionManager | Any | None = None,
) -> DatabaseSessionManager | Any:
    """Resolve the DB handle that repositories should bind to.

    FastAPI routes should use the shared session manager. Tests and direct
    function calls sometimes initialize ``database_proxy`` without booting the
    API lifespan, so this helper reuses that bound database for compatibility.
    """
    if session_manager is not None:
        return session_manager

    proxy_target = getattr(database_proxy, "obj", None)
    if proxy_target is not None:
        return proxy_target

    if _session_manager is not None:
        return _session_manager

    return get_session_manager()


def get_request_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteRequestRepositoryAdapter:
    """Build a request repository bound to the shared session manager."""
    return SqliteRequestRepositoryAdapter(resolve_repository_session(session_manager))


def get_summary_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteSummaryRepositoryAdapter:
    """Build a summary repository bound to the shared session manager."""
    return SqliteSummaryRepositoryAdapter(resolve_repository_session(session_manager))


def get_crawl_result_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteCrawlResultRepositoryAdapter:
    """Build a crawl-result repository bound to the shared session manager."""
    return SqliteCrawlResultRepositoryAdapter(resolve_repository_session(session_manager))


def get_llm_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteLLMRepositoryAdapter:
    """Build an LLM repository bound to the shared session manager."""
    return SqliteLLMRepositoryAdapter(resolve_repository_session(session_manager))


def get_user_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteUserRepositoryAdapter:
    """Build a user repository bound to the shared session manager."""
    return SqliteUserRepositoryAdapter(resolve_repository_session(session_manager))


def get_auth_repository(
    token_cache: Any | None = None,
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteAuthRepositoryAdapter:
    """Build an auth repository bound to the shared session manager."""
    return SqliteAuthRepositoryAdapter(
        resolve_repository_session(session_manager),
        token_cache=token_cache,
    )


def get_collection_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteCollectionRepositoryAdapter:
    """Build a collection repository bound to the shared session manager."""
    return SqliteCollectionRepositoryAdapter(resolve_repository_session(session_manager))


def get_device_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteDeviceRepositoryAdapter:
    """Build a device repository bound to the shared session manager."""
    return SqliteDeviceRepositoryAdapter(resolve_repository_session(session_manager))


def get_topic_search_repository(
    session_manager: DatabaseSessionManager | None = None,
) -> SqliteTopicSearchRepositoryAdapter:
    """Build a topic-search repository bound to the shared session manager."""
    return SqliteTopicSearchRepositoryAdapter(resolve_repository_session(session_manager))


def get_summary_read_model_use_case(
    session_manager: DatabaseSessionManager | None = None,
) -> SummaryReadModelUseCase:
    """Build the summary read-model use case with shared DB wiring."""
    manager = resolve_repository_session(session_manager)
    return SummaryReadModelUseCase(
        summary_repository=get_summary_repository(manager),
        request_repository=get_request_repository(manager),
        crawl_result_repository=get_crawl_result_repository(manager),
        llm_repository=get_llm_repository(manager),
    )


def get_search_read_model_use_case(
    session_manager: DatabaseSessionManager | None = None,
) -> SearchReadModelUseCase:
    """Build the search read-model use case with shared DB wiring."""
    manager = resolve_repository_session(session_manager)
    return SearchReadModelUseCase(
        topic_search_repository=get_topic_search_repository(manager),
        request_repository=get_request_repository(manager),
        summary_repository=get_summary_repository(manager),
    )


@lru_cache(maxsize=1)
def _get_db_config() -> DatabaseConfig:
    """Get database configuration from environment."""
    # Pydantic handles string-to-number coercion at runtime via validation_alias
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
