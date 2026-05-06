"""Database access helpers backed by the shared API runtime."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from app.application.use_cases.search_read_model import SearchReadModelUseCase
from app.application.use_cases.summary_read_model import SummaryReadModelUseCase
from app.core.logging_utils import get_logger
from app.di.database import clear_cached_runtime_database, get_or_create_runtime_database_from_env

if TYPE_CHECKING:
    from app.application.ports.requests import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
    )
    from app.application.ports.search import TopicSearchRepositoryPort
    from app.application.ports.summaries import SummaryRepositoryPort
    from app.application.ports.users import UserRepositoryPort
    from app.db.session import Database

logger = get_logger(__name__)


def get_session_manager(request: Any = None) -> Database:
    """Resolve the shared API database facade."""
    from app.di.api import resolve_api_runtime

    try:
        return resolve_api_runtime(request).db
    except RuntimeError:
        manager = get_or_create_runtime_database_from_env(migrate=True)
        logger.info(
            "session_manager_initialized",
            extra={"database_dsn": _redact_dsn(manager.config.dsn)},
        )
        return manager


def clear_session_manager() -> None:
    """Reset API runtime and fallback DB state used in tests."""
    with contextlib.suppress(Exception):
        from app.di.api import get_current_api_runtime

        runtime = get_current_api_runtime()
        database = getattr(runtime.db, "dispose", None)
        if database is not None:
            # clear_cached_runtime_database disposes the fallback DB; runtime-owned
            # databases are disposed by the FastAPI lifespan once O3 ports it.
            pass
    with contextlib.suppress(Exception):
        from app.di.api import clear_current_api_runtime

        clear_current_api_runtime()
    clear_cached_runtime_database()


def resolve_repository_session(
    session_manager: Database | Any | None = None,
    request: Any = None,
) -> Database | Any:
    """Resolve the DB handle repositories should bind to."""
    if session_manager is not None:
        return session_manager

    with contextlib.suppress(RuntimeError):
        from app.di.api import resolve_api_runtime

        return resolve_api_runtime(request).db

    return get_session_manager(request)


def get_request_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> RequestRepositoryPort:
    """Build a request repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.request_repository import (
        SqliteRequestRepositoryAdapter,
    )

    return SqliteRequestRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_summary_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> SummaryRepositoryPort:
    """Build a summary repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.summary_repository import (
        SqliteSummaryRepositoryAdapter,
    )

    return SqliteSummaryRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_crawl_result_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> CrawlResultRepositoryPort:
    """Build a crawl-result repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.crawl_result_repository import (
        SqliteCrawlResultRepositoryAdapter,
    )

    return SqliteCrawlResultRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_llm_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> LLMRepositoryPort:
    """Build an LLM repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.llm_repository import (
        SqliteLLMRepositoryAdapter,
    )

    return SqliteLLMRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_user_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> UserRepositoryPort:
    """Build a user repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )

    return SqliteUserRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_auth_repository(
    token_cache: Any | None = None,
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build an auth repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.auth_repository import (
        SqliteAuthRepositoryAdapter,
    )

    return SqliteAuthRepositoryAdapter(
        resolve_repository_session(session_manager, request),
        token_cache=token_cache,
    )


def get_collection_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a collection repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.collection_repository import (
        SqliteCollectionRepositoryAdapter,
    )

    return SqliteCollectionRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_device_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a device repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.device_repository import (
        SqliteDeviceRepositoryAdapter,
    )

    return SqliteDeviceRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_backup_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a backup repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.backup_repository import (
        SqliteBackupRepositoryAdapter,
    )

    return SqliteBackupRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_rule_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a rule repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.rule_repository import (
        SqliteRuleRepositoryAdapter,
    )

    return SqliteRuleRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_webhook_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a webhook repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.webhook_repository import (
        SqliteWebhookRepositoryAdapter,
    )

    return SqliteWebhookRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_import_job_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build an import-job repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.import_job_repository import (
        SqliteImportJobRepositoryAdapter,
    )

    return SqliteImportJobRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_bookmark_import_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build a bookmark-import repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.bookmark_import_repository import (
        SqliteBookmarkImportAdapter,
    )

    return SqliteBookmarkImportAdapter(resolve_repository_session(session_manager, request))


def get_audio_generation_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> Any:
    """Build an audio-generation repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.audio_generation_repository import (
        SqliteAudioGenerationRepositoryAdapter,
    )

    return SqliteAudioGenerationRepositoryAdapter(
        resolve_repository_session(session_manager, request)
    )


def get_topic_search_repository(
    session_manager: Database | None = None,
    request: Any = None,
) -> TopicSearchRepositoryPort:
    """Build a topic-search repository bound to the shared session manager."""
    from app.infrastructure.persistence.repositories.topic_search_repository import (
        SqliteTopicSearchRepositoryAdapter,
    )

    return SqliteTopicSearchRepositoryAdapter(resolve_repository_session(session_manager, request))


def get_summary_read_model_use_case(
    session_manager: Database | None = None,
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
        from app.di.api import resolve_api_runtime

        return resolve_api_runtime(request).summary_read_model_use_case
    manager = resolve_repository_session(session_manager, request)
    return SummaryReadModelUseCase(
        summary_repository=get_summary_repository(manager, request),
        request_repository=get_request_repository(manager, request),
        crawl_result_repository=get_crawl_result_repository(manager, request),
        llm_repository=get_llm_repository(manager, request),
    )


def get_search_read_model_use_case(
    session_manager: Database | None = None,
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
        from app.di.api import resolve_api_runtime

        return resolve_api_runtime(request).search_read_model_use_case
    manager = resolve_repository_session(session_manager, request)
    return SearchReadModelUseCase(
        topic_search_repository=get_topic_search_repository(manager, request),
        request_repository=get_request_repository(manager, request),
        summary_repository=get_summary_repository(manager, request),
    )


def _redact_dsn(dsn: str) -> str:
    if "@" not in dsn:
        return dsn
    prefix, suffix = dsn.rsplit("@", 1)
    if ":" not in prefix:
        return f"...@{suffix}"
    scheme_user, _password = prefix.rsplit(":", 1)
    return f"{scheme_user}:***@{suffix}"
