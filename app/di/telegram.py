from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.attachment.attachment_processor import AttachmentProcessor
from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.command_dispatcher import TelegramCommandDispatcher
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.telegram.message_router import MessageRouter
from app.adapters.telegram.task_manager import UserTaskManager
from app.adapters.telegram.telegram_client import TelegramClient
from app.adapters.telegram.url_handler import URLHandler
from app.application.services.adaptive_timeout import AdaptiveTimeoutService
from app.application.services.related_reads_service import RelatedReadsService
from app.application.services.tts_service import TTSService
from app.core.logging_utils import get_logger
from app.core.verbosity import VerbosityResolver
from app.di.application import build_application_services
from app.di.repositories import (
    build_audit_log_repository,
    build_batch_session_repository,
    build_embedding_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_topic_search_repository,
    build_user_repository,
)
from app.di.search import build_search_dependencies, get_topic_search_limit
from app.di.shared import build_async_audit_sink, build_core_dependencies, build_url_processor
from app.di.telegram_commands import build_command_dispatcher_deps as _build_command_dispatcher_deps
from app.di.types import (
    SummaryCliRuntime,
    TelegramCommandDispatcherDeps,
    TelegramRepositories,
    TelegramRuntime,
)
from app.infrastructure.audio.elevenlabs_provider import ElevenLabsTTSProviderAdapter
from app.infrastructure.audio.filesystem_storage import FileSystemAudioStorageAdapter
from app.infrastructure.persistence.sqlite.repositories.audio_generation_repository import (
    SqliteAudioGenerationRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.latency_stats_repository import (
    SqliteLatencyStatsRepositoryAdapter,
)
from app.infrastructure.search.vector_search_port_adapter import VectorSearchPortAdapter
from app.infrastructure.search.vector_search_service import VectorSearchService
from app.security.file_validation import SecureFileValidator

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _TelegramProcessingStack:
    url_processor: Any
    forward_processor: Any
    attachment_processor: Any


@dataclass(frozen=True, slots=True)
class _TelegramInterfaceStack:
    telegram_client: TelegramClient
    adaptive_timeout_service: AdaptiveTimeoutService | None
    task_manager: UserTaskManager
    url_handler: URLHandler
    command_dispatcher: TelegramCommandDispatcher
    access_controller: AccessController
    callback_handler: CallbackHandler
    message_handler: MessageHandler


def build_telegram_runtime(
    cfg: AppConfig,
    db: DatabaseSessionManager,
    *,
    safe_reply_func: Any,
    reply_json_func: Any,
    db_write_queue: DbWriteQueue | None = None,
    audit_task_registry: set[Any] | None = None,
) -> TelegramRuntime:
    """Build the full Telegram runtime graph from shared DI modules."""
    telegram_repositories = _build_telegram_repositories(db)
    verbosity_resolver = VerbosityResolver(telegram_repositories.user_repository)
    audit_sink = build_async_audit_sink(db, task_registry=audit_task_registry)
    core = build_core_dependencies(
        cfg,
        db,
        audit_sink=audit_sink,
        response_formatter_kwargs={
            "safe_reply_func": safe_reply_func,
            "reply_json_func": reply_json_func,
            "verbosity_resolver": verbosity_resolver,
            "admin_log_chat_id": cfg.telegram.admin_log_chat_id,
        },
    )
    topic_search_max_results = get_topic_search_limit(cfg)
    search = _build_search_stack(
        cfg=cfg,
        db=db,
        llm_client=core.llm_client,
        audit_func=core.audit_sink,
        firecrawl_client=core.firecrawl_client,
        topic_search_max_results=topic_search_max_results,
    )
    processing = _build_processing_stack(
        cfg=cfg,
        db=db,
        core=core,
        search=search,
        repositories=telegram_repositories,
        db_write_queue=db_write_queue,
    )
    application_services = build_application_services(
        db,
        topic_search_service=search.local_searcher,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )
    interface = _build_telegram_interface_stack(
        cfg=cfg,
        db=db,
        core=core,
        search=search,
        repositories=telegram_repositories,
        processing=processing,
        application_services=application_services,
        audit_func=audit_sink,
        verbosity_resolver=verbosity_resolver,
    )

    logger.info(
        "telegram_runtime_initialized",
        extra={
            "topic_search_max_results": topic_search_max_results,
            "vector_search_enabled": search.chroma_vector_search_service is not None,
        },
    )
    return TelegramRuntime(
        core=core,
        search=search,
        application_services=application_services,
        telegram_client=interface.telegram_client,
        response_formatter=core.response_formatter,
        url_processor=processing.url_processor,
        forward_processor=processing.forward_processor,
        attachment_processor=processing.attachment_processor,
        message_handler=interface.message_handler,
        adaptive_timeout_service=interface.adaptive_timeout_service,
        verbosity_resolver=verbosity_resolver,
    )


def build_summary_cli_runtime(
    cfg: AppConfig,
    db: DatabaseSessionManager,
) -> SummaryCliRuntime:
    """Build the CLI summary runtime using the same shared resources as Telegram."""
    repositories = _build_telegram_repositories(db)
    audit_sink = build_async_audit_sink(db)
    core = build_core_dependencies(cfg, db, audit_sink=audit_sink)
    search = _build_search_stack(
        cfg=cfg,
        db=db,
        llm_client=core.llm_client,
        audit_func=core.audit_sink,
        firecrawl_client=core.firecrawl_client,
        topic_search_max_results=None,
    )
    url_processor = build_url_processor(
        cfg=cfg,
        db=db,
        firecrawl=core.scraper_chain,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        topic_search=search.topic_searcher if cfg.web_search.enabled else None,
        request_repo=repositories.request_repository,
        summary_repo=repositories.summary_repository,
    )
    application_services = build_application_services(
        db,
        topic_search_service=search.local_searcher,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )
    url_handler = URLHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        user_repo=repositories.user_repository,
        request_repo=repositories.request_repository,
    )
    dispatcher_deps = _build_command_dispatcher_deps(
        cfg=cfg,
        db=db,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        url_processor=url_processor,
        url_handler=url_handler,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        task_manager=None,
        hybrid_search=search.hybrid_search_service,
        verbosity_resolver=None,
        application_services=application_services,
        repositories=repositories,
        tts_service_factory=_build_tts_service_factory(
            cfg=cfg,
            db=db,
            summary_repo=repositories.summary_repository,
        ),
    )
    command_processor = _build_command_dispatcher(dispatcher_deps)
    return SummaryCliRuntime(
        core=core,
        search=search,
        application_services=application_services,
        url_processor=url_processor,
        command_processor=command_processor,
    )


def _build_telegram_repositories(db: DatabaseSessionManager) -> TelegramRepositories:
    return TelegramRepositories(
        user_repository=build_user_repository(db),
        summary_repository=build_summary_repository(db),
        request_repository=build_request_repository(db),
        llm_repository=build_llm_repository(db),
        audit_log_repository=build_audit_log_repository(db),
        batch_session_repository=build_batch_session_repository(db),
    )


def _build_search_stack(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    llm_client: Any,
    audit_func: Any,
    firecrawl_client: Any,
    topic_search_max_results: int | None,
) -> Any:
    return build_search_dependencies(
        cfg,
        db,
        llm_client=llm_client,
        audit_func=audit_func,
        firecrawl_client=firecrawl_client,
        topic_search_max_results=topic_search_max_results,
    )


def _build_processing_stack(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    core: Any,
    search: Any,
    repositories: TelegramRepositories,
    db_write_queue: DbWriteQueue | None,
) -> _TelegramProcessingStack:
    url_processor = build_url_processor(
        cfg=cfg,
        db=db,
        firecrawl=core.scraper_chain,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        topic_search=search.topic_searcher if cfg.web_search.enabled else None,
        db_write_queue=db_write_queue,
        request_repo=repositories.request_repository,
        summary_repo=repositories.summary_repository,
    )
    forward_processor = ForwardProcessor(
        cfg=cfg,
        db=db,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        db_write_queue=db_write_queue,
        summary_repo=repositories.summary_repository,
        request_repo=repositories.request_repository,
        user_repo=repositories.user_repository,
    )
    attachment_processor = AttachmentProcessor(
        cfg=cfg,
        db=db,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        db_write_queue=db_write_queue,
        request_repo=repositories.request_repository,
        user_repo=repositories.user_repository,
    )
    _wire_related_reads(
        cfg=cfg,
        db=db,
        search=search,
        url_processor=url_processor,
        forward_processor=forward_processor,
    )
    return _TelegramProcessingStack(
        url_processor=url_processor,
        forward_processor=forward_processor,
        attachment_processor=attachment_processor,
    )


def _build_telegram_interface_stack(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    core: Any,
    search: Any,
    repositories: TelegramRepositories,
    processing: _TelegramProcessingStack,
    application_services: Any,
    audit_func: Any,
    verbosity_resolver: VerbosityResolver,
) -> _TelegramInterfaceStack:
    telegram_client = TelegramClient(cfg=cfg)
    core.response_formatter.set_telegram_client(telegram_client)
    _configure_forum_topics(
        cfg=cfg,
        response_formatter=core.response_formatter,
        telegram_client=telegram_client,
    )

    adaptive_timeout_service = _create_adaptive_timeout_service(cfg=cfg, db=db)
    task_manager = UserTaskManager()
    url_handler = URLHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_processor=processing.url_processor,
        adaptive_timeout_service=adaptive_timeout_service,
        verbosity_resolver=verbosity_resolver,
        llm_client=core.llm_client,
        batch_session_repo=repositories.batch_session_repository,
        batch_config=cfg.batch_analysis,
        user_repo=repositories.user_repository,
        request_repo=repositories.request_repository,
        file_validator=SecureFileValidator(max_file_size=10 * 1024 * 1024),
    )
    dispatcher_deps = _build_command_dispatcher_deps(
        cfg=cfg,
        db=db,
        response_formatter=core.response_formatter,
        audit_func=audit_func,
        url_processor=processing.url_processor,
        url_handler=url_handler,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        task_manager=task_manager,
        hybrid_search=search.hybrid_search_service,
        verbosity_resolver=verbosity_resolver,
        application_services=application_services,
        repositories=repositories,
        tts_service_factory=_build_tts_service_factory(
            cfg=cfg,
            db=db,
            summary_repo=repositories.summary_repository,
        ),
    )
    command_dispatcher = _build_command_dispatcher(dispatcher_deps)
    access_controller = AccessController(
        cfg=cfg,
        db=db,
        response_formatter=core.response_formatter,
        audit_func=audit_func,
        user_repo=repositories.user_repository,
    )
    lang = getattr(core.response_formatter, "_lang", "en")
    callback_handler = CallbackHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_handler=url_handler,
        hybrid_search=search.hybrid_search_service,
        lang=lang,
    )
    message_router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=access_controller,
        command_processor=command_dispatcher,
        url_handler=url_handler,
        forward_processor=processing.forward_processor,
        response_formatter=core.response_formatter,
        audit_func=audit_func,
        task_manager=task_manager,
        attachment_processor=processing.attachment_processor,
        user_repo=repositories.user_repository,
        callback_handler=callback_handler,
        lang=lang,
    )
    message_handler = MessageHandler(
        cfg=cfg,
        db=db,
        audit_repo=repositories.audit_log_repository,
        task_manager=task_manager,
        access_controller=access_controller,
        url_handler=url_handler,
        command_dispatcher=command_dispatcher,
        callback_handler=callback_handler,
        message_router=message_router,
        url_processor=processing.url_processor,
    )
    return _TelegramInterfaceStack(
        telegram_client=telegram_client,
        adaptive_timeout_service=adaptive_timeout_service,
        task_manager=task_manager,
        url_handler=url_handler,
        command_dispatcher=command_dispatcher,
        access_controller=access_controller,
        callback_handler=callback_handler,
        message_handler=message_handler,
    )


def _build_tts_service_factory(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    summary_repo: Any,
) -> Any:
    return lambda: TTSService(
        summary_repository=summary_repo,
        audio_generation_repository=SqliteAudioGenerationRepositoryAdapter(db),
        tts_provider=ElevenLabsTTSProviderAdapter(cfg.tts),
        audio_storage=FileSystemAudioStorageAdapter(cfg.tts.audio_storage_path),
        voice_id=cfg.tts.voice_id,
        model_name=cfg.tts.model,
        max_chars_per_request=cfg.tts.max_chars_per_request,
    )


def _build_command_dispatcher(
    dispatcher_deps: TelegramCommandDispatcherDeps,
) -> TelegramCommandDispatcher:
    return TelegramCommandDispatcher(
        routes=dispatcher_deps.routes,
        runtime_state=dispatcher_deps.runtime_state,
        context_factory=dispatcher_deps.context_factory,
        onboarding_handler=dispatcher_deps.onboarding_handler,
        admin_handler=dispatcher_deps.admin_handler,
        url_commands_handler=dispatcher_deps.url_commands_handler,
        content_handler=dispatcher_deps.content_handler,
        search_handler=dispatcher_deps.search_handler,
        listen_handler=dispatcher_deps.listen_handler,
        digest_handler=dispatcher_deps.digest_handler,
        init_session_handler=dispatcher_deps.init_session_handler,
        settings_handler=dispatcher_deps.settings_handler,
        tag_handler=dispatcher_deps.tag_handler,
        rules_handler=dispatcher_deps.rules_handler,
        export_handler=dispatcher_deps.export_handler,
        backup_handler=dispatcher_deps.backup_handler,
    )


def _configure_forum_topics(
    *,
    cfg: AppConfig,
    response_formatter: Any,
    telegram_client: TelegramClient,
) -> None:
    if not cfg.telegram.forum_topics_enabled:
        return
    from app.adapters.telegram.topic_manager import TopicManager

    topic_manager = TopicManager()
    response_formatter.set_topic_manager(topic_manager)
    telegram_client.topic_manager = topic_manager
    logger.info("forum_topic_manager_initialized")


def _create_adaptive_timeout_service(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
) -> AdaptiveTimeoutService | None:
    if cfg.adaptive_timeout is None:
        return None
    try:
        service = AdaptiveTimeoutService(
            config=cfg.adaptive_timeout,
            repository=SqliteLatencyStatsRepositoryAdapter(db),
        )
        logger.info(
            "adaptive_timeout_service_initialized",
            extra={
                "enabled": cfg.adaptive_timeout.enabled,
                "default_timeout_sec": cfg.adaptive_timeout.default_timeout_sec,
                "min_timeout_sec": cfg.adaptive_timeout.min_timeout_sec,
                "max_timeout_sec": cfg.adaptive_timeout.max_timeout_sec,
            },
        )
        return service
    except Exception as exc:
        logger.warning(
            "adaptive_timeout_service_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
            exc_info=True,
        )
        return None


def _wire_related_reads(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    search: Any,
    url_processor: URLProcessor,
    forward_processor: ForwardProcessor,
) -> None:
    if not cfg.runtime.related_reads_enabled:
        return
    try:
        vector_search_service = VectorSearchService(
            embedding_repository=build_embedding_repository(db),
            topic_search_repository=build_topic_search_repository(db),
            embedding_service=search.embedding_service,
            max_results=10,
            min_similarity=0.3,
        )
        related_reads_service = RelatedReadsService(
            VectorSearchPortAdapter(vector_search_service),
            min_similarity=cfg.runtime.related_reads_min_similarity,
        )
        url_processor.post_summary_tasks._related_reads_service = related_reads_service
        forward_processor._related_reads_service = related_reads_service
        logger.info("related_reads_service_initialized")
    except Exception as exc:
        logger.warning(
            "related_reads_service_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
            exc_info=True,
        )
