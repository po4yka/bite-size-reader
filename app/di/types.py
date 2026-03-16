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
class TelegramRuntime:
    core: CoreDependencies
    search: SearchDependencies
    telegram_client: Any
    response_formatter: Any
    url_processor: Any
    forward_processor: Any
    attachment_processor: Any
    message_handler: Any
    adaptive_timeout_service: Any | None = None
    verbosity_resolver: Any | None = None
    container: Any | None = None


@dataclass(frozen=True, slots=True)
class SummaryCliRuntime:
    core: CoreDependencies
    search: SearchDependencies
    url_processor: Any
    command_processor: Any
    container: Any | None = None


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    cfg: AppConfig
    db: DatabaseSessionManager
    redis_client: Any | None
    core: CoreDependencies
    search: SearchDependencies
    background_processor: Any
    summary_read_model_use_case: Any
    search_read_model_use_case: Any
    sync_service: Any


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
    karakeep_service_factory: Callable[[], Any]
    karakeep_user_id_resolver: Callable[[], int | None]
    digest_userbot_factory: Callable[[], Any]
    digest_llm_factory: Callable[[], Any]
    digest_bot_client_factory: Callable[[], Any]
    digest_service_factory: Callable[
        [Any, Any, Callable[[int, str, Any | None], Awaitable[None]]], Any
    ]
