"""Database access helpers backed by the shared API runtime."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from app.application.use_cases.search_read_model import SearchReadModelUseCase
from app.application.use_cases.summary_read_model import SummaryReadModelUseCase
from app.core.logging_utils import get_logger
from app.db.models import database_proxy
from app.di.api import clear_current_api_runtime, get_current_api_runtime, resolve_api_runtime
from app.di.database import clear_cached_runtime_database, get_or_create_runtime_database_from_env
from app.infrastructure.persistence.sqlite.repositories.audio_generation_repository import (
    SqliteAudioGenerationRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
    SqliteAuthRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.backup_repository import (
    SqliteBackupRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.bookmark_import_repository import (
    SqliteBookmarkImportAdapter,
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
from app.infrastructure.persistence.sqlite.repositories.import_job_repository import (
    SqliteImportJobRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.rule_repository import (
    SqliteRuleRepositoryAdapter,
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
from app.infrastructure.persistence.sqlite.repositories.webhook_repository import (
    SqliteWebhookRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.application.ports.requests import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
    )
    from app.application.ports.search import TopicSearchRepositoryPort
    from app.application.ports.summaries import SummaryRepositoryPort
    from app.application.ports.users import UserRepositoryPort
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def get_session_manager(request: Any = None) -> DatabaseSessionManager:
    """Resolve the shared API database session manager."""
    try:
        return resolve_api_runtime(request).db
    except RuntimeError:
        manager = get_or_create_runtime_database_from_env(migrate=True)
        logger.info(
            "session_manager_initialized",
            extra={"db_path": getattr(manager, "path", None)},
        )
        return manager


def clear_session_manager() -> None:
    """Reset API runtime and fallback DB state used in tests."""
    with contextlib.suppress(RuntimeError):
        runtime = get_current_api_runtime()
        database = getattr(runtime.db, "database", None)
        if database is not None:
            database.close()
    clear_current_api_runtime()
    clear_cached_runtime_database()


def resolve_repository_session(
    session_manager: DatabaseSessionManager | Any | None = None,
    request: Any = None,
) -> DatabaseSessionManager | Any:
    """Resolve the DB handle repositories should bind to."""
    if session_manager is not None:
        return session_manager

    with contextlib.suppress(RuntimeError):
        return resolve_api_runtime(request).db

    proxy_target = getattr(database_proxy, "obj", None)
    if proxy_target is not None and hasattr(proxy_target, "async_execute"):
        return proxy_target

    return get_session_manager(request)


def get_request_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> RequestRepositoryPort:
    """Build a request repository bound to the shared session manager."""
    return SqliteRequestRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_summary_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SummaryRepositoryPort:
    """Build a summary repository bound to the shared session manager."""
    return SqliteSummaryRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_crawl_result_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> CrawlResultRepositoryPort:
    """Build a crawl-result repository bound to the shared session manager."""
    return SqliteCrawlResultRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_llm_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> LLMRepositoryPort:
    """Build an LLM repository bound to the shared session manager."""
    return SqliteLLMRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_user_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> UserRepositoryPort:
    """Build a user repository bound to the shared session manager."""
    return SqliteUserRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_auth_repository(
    token_cache: Any | None = None,
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteAuthRepositoryAdapter:
    """Build an auth repository bound to the shared session manager."""
    return SqliteAuthRepositoryAdapter(
        resolve_repository_session(session_manager, request),
        token_cache=token_cache,
    )


def get_collection_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteCollectionRepositoryAdapter:
    """Build a collection repository bound to the shared session manager."""
    return SqliteCollectionRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_device_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteDeviceRepositoryAdapter:
    """Build a device repository bound to the shared session manager."""
    return SqliteDeviceRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_backup_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteBackupRepositoryAdapter:
    """Build a backup repository bound to the shared session manager."""
    return SqliteBackupRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_rule_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteRuleRepositoryAdapter:
    """Build a rule repository bound to the shared session manager."""
    return SqliteRuleRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_webhook_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteWebhookRepositoryAdapter:
    """Build a webhook repository bound to the shared session manager."""
    return SqliteWebhookRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_import_job_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteImportJobRepositoryAdapter:
    """Build an import-job repository bound to the shared session manager."""
    return SqliteImportJobRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_bookmark_import_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteBookmarkImportAdapter:
    """Build a bookmark-import repository bound to the shared session manager."""
    return SqliteBookmarkImportAdapter(resolve_repository_session(session_manager, request))


def get_audio_generation_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SqliteAudioGenerationRepositoryAdapter:
    """Build an audio-generation repository bound to the shared session manager."""
    return SqliteAudioGenerationRepositoryAdapter(
        resolve_repository_session(session_manager, request)
    )


def get_topic_search_repository(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> TopicSearchRepositoryPort:
    """Build a topic-search repository bound to the shared session manager."""
    return SqliteTopicSearchRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_summary_read_model_use_case(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SummaryReadModelUseCase:
    """Resolve the shared summary read-model use case from API runtime."""
    if session_manager is not None:
        manager = resolve_repository_session(session_manager, request)
        return SummaryReadModelUseCase(
            summary_repository=get_summary_repository(manager, request),
            request_repository=get_request_repository(manager, request),
            crawl_result_repository=get_crawl_result_repository(manager, request),
            llm_repository=get_llm_repository(manager, request),
        )
    with contextlib.suppress(RuntimeError):
        return resolve_api_runtime(request).summary_read_model_use_case
    manager = resolve_repository_session(session_manager, request)
    return SummaryReadModelUseCase(
        summary_repository=get_summary_repository(manager, request),
        request_repository=get_request_repository(manager, request),
        crawl_result_repository=get_crawl_result_repository(manager, request),
        llm_repository=get_llm_repository(manager, request),
    )


def get_search_read_model_use_case(
    session_manager: DatabaseSessionManager | None = None,
    request: Any = None,
) -> SearchReadModelUseCase:
    """Resolve the shared search read-model use case from API runtime."""
    if session_manager is not None:
        manager = resolve_repository_session(session_manager, request)
        return SearchReadModelUseCase(
            topic_search_repository=get_topic_search_repository(manager, request),
            request_repository=get_request_repository(manager, request),
            summary_repository=get_summary_repository(manager, request),
        )
    with contextlib.suppress(RuntimeError):
        return resolve_api_runtime(request).search_read_model_use_case
    manager = resolve_repository_session(session_manager, request)
    return SearchReadModelUseCase(
        topic_search_repository=get_topic_search_repository(manager, request),
        request_repository=get_request_repository(manager, request),
        summary_repository=get_summary_repository(manager, request),
    )
