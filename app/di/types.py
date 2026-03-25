from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


@dataclass(frozen=True, slots=True)
class CoreDependencies:
    cfg: AppConfig
    db: DatabaseSessionManager
    audit_sink: Callable[[str, str, dict[str, Any]], None]
    semaphore_factory: Callable[[], Any]
    llm_client: Any
    scraper_chain: Any
    response_formatter: Any
    firecrawl_client: Any | None = None


@dataclass(frozen=True, slots=True)
class SearchDependencies:
    local_searcher: Any
    topic_searcher: Any | None
    embedding_service: Any
    embedding_generator: Any
    vector_store: Any | None
    chroma_vector_search_service: Any | None
    hybrid_search_service: Any
    query_expansion_service: Any | None = None


@dataclass(frozen=True, slots=True)
class TelegramRepositories:
    user_repository: Any
    summary_repository: Any
    request_repository: Any
    crawl_result_repository: Any
    llm_repository: Any
    tag_repository: Any
    audit_log_repository: Any
    batch_session_repository: Any


@dataclass(frozen=True, slots=True)
class TelegramCommandDispatcherDeps:
    routes: Any
    runtime_state: Any
    context_factory: Any
    onboarding_handler: Any
    admin_handler: Any
    url_commands_handler: Any
    content_handler: Any
    search_handler: Any
    listen_handler: Any
    digest_handler: Any
    init_session_handler: Any
    settings_handler: Any
    tag_handler: Any
    rules_handler: Any
    export_handler: Any
    backup_handler: Any


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    unread_summaries: Any
    mark_summary_as_read: Any
    mark_summary_as_unread: Any
    search_topics: Any | None
    event_bus: Any


@dataclass(frozen=True, slots=True)
class TelegramRuntime:
    core: CoreDependencies
    search: SearchDependencies
    application_services: ApplicationServices
    telegram_client: Any
    response_formatter: Any
    url_processor: Any
    forward_processor: Any
    attachment_processor: Any
    message_handler: Any
    adaptive_timeout_service: Any | None = None
    verbosity_resolver: Any | None = None


@dataclass(frozen=True, slots=True)
class SummaryCliRuntime:
    core: CoreDependencies
    search: SearchDependencies
    application_services: ApplicationServices
    url_processor: Any
    command_processor: Any


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    cfg: AppConfig
    db: DatabaseSessionManager
    database_services: Any | None
    redis_client: Any | None
    core: CoreDependencies
    search: SearchDependencies
    background_processor: Any
    summary_read_model_use_case: Any
    search_read_model_use_case: Any
    request_service: Any
    sync_service: Any
    tag_repo: Any = None
    rss_feed_repo: Any = None


@dataclass(slots=True)
class McpScope:
    user_id: int | None = None


@dataclass(slots=True)
class McpServiceState:
    service: Any | None = None
    last_failed_at: float | None = None
    init_lock: Any | None = None
    resources: tuple[Any, ...] = ()


@dataclass(slots=True)
class McpRuntime:
    cfg: AppConfig | None
    db_path: str
    database: Any
    scope: McpScope
    chroma_state: McpServiceState = field(default_factory=McpServiceState)
    local_vector_state: McpServiceState = field(default_factory=McpServiceState)


@dataclass(frozen=True, slots=True)
class SchedulerDependencies:
    digest_userbot_factory: Callable[[], Any]
    digest_llm_factory: Callable[[], Any]
    digest_bot_client_factory: Callable[[], Any]
    digest_service_factory: Callable[
        [Any, Any, Callable[[int, str, Any | None], Awaitable[None]]], Any
    ]
    rss_bot_client_factory: Callable[[], Any] | None = None
    rss_delivery_factory: Callable[[], Any] | None = None


@dataclass(frozen=True, slots=True)
class BackgroundProcessorDeps:
    request_repository: Any
    summary_repository: Any
    db_override_factory: Any
    lock_manager: Any
    retry_runner: Any
    progress_publisher: Any
    failure_handler: Any
    url_handler: Any
    forward_handler: Any


@dataclass(frozen=True, slots=True)
class SyncDeps:
    user_repository: Any
    request_repository: Any
    summary_repository: Any
    crawl_result_repository: Any
    llm_repository: Any
    session_store: Any
    aux_read_port: Any
    record_collector: Any
    envelope_serializer: Any
    apply_service: Any


@dataclass(frozen=True, slots=True)
class DatabaseRuntimeServices:
    executor: Any
    bootstrap: Any
    maintenance: Any
    inspection: Any
    backups: Any
