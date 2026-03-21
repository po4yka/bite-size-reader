from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.attachment.attachment_processor import AttachmentProcessor
from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.command_dispatcher import TelegramCommandDispatcher
from app.adapters.telegram.command_handlers.karakeep_handler import KarakeepHandler
from app.adapters.telegram.command_handlers.listen_handler import ListenHandler
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
    build_karakeep_sync_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_topic_search_repository,
    build_user_repository,
)
from app.di.search import build_search_dependencies, get_topic_search_limit
from app.di.shared import build_async_audit_sink, build_core_dependencies, build_url_processor
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
    user_repo = build_user_repository(db)
    summary_repo = build_summary_repository(db)
    request_repo = build_request_repository(db)
    llm_repo = build_llm_repository(db)
    audit_repo = build_audit_log_repository(db)
    batch_session_repo = build_batch_session_repository(db)
    karakeep_sync_repo = build_karakeep_sync_repository(db)
    telegram_repositories = TelegramRepositories(
        user_repository=user_repo,
        summary_repository=summary_repo,
        request_repository=request_repo,
        llm_repository=llm_repo,
        audit_log_repository=audit_repo,
        batch_session_repository=batch_session_repo,
        karakeep_sync_repository=karakeep_sync_repo,
    )
    verbosity_resolver = VerbosityResolver(user_repo)
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
    search = build_search_dependencies(
        cfg,
        db,
        llm_client=core.llm_client,
        audit_func=core.audit_sink,
        firecrawl_client=core.firecrawl_client,
        topic_search_max_results=topic_search_max_results,
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
        db_write_queue=db_write_queue,
    )
    forward_processor = ForwardProcessor(
        cfg=cfg,
        db=db,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        db_write_queue=db_write_queue,
        summary_repo=summary_repo,
        request_repo=request_repo,
        user_repo=user_repo,
    )
    attachment_processor = AttachmentProcessor(
        cfg=cfg,
        db=db,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        db_write_queue=db_write_queue,
        request_repo=request_repo,
        user_repo=user_repo,
    )

    _wire_related_reads(
        cfg=cfg,
        db=db,
        search=search,
        url_processor=url_processor,
        forward_processor=forward_processor,
    )

    application_services = build_application_services(
        db,
        topic_search_service=search.local_searcher,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )

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
        url_processor=url_processor,
        adaptive_timeout_service=adaptive_timeout_service,
        verbosity_resolver=verbosity_resolver,
        llm_client=core.llm_client,
        batch_session_repo=batch_session_repo,
        batch_config=cfg.batch_analysis,
        user_repo=user_repo,
        request_repo=request_repo,
        file_validator=SecureFileValidator(max_file_size=10 * 1024 * 1024),
    )
    dispatcher_deps = TelegramCommandDispatcherDeps(
        user_repository=user_repo,
        response_formatter=core.response_formatter,
        audit_func=audit_sink,
        url_processor=url_processor,
        url_handler=url_handler,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        task_manager=task_manager,
        hybrid_search=search.hybrid_search_service,
        verbosity_resolver=verbosity_resolver,
        application_services=application_services,
        repositories=telegram_repositories,
        handlers={
            "karakeep": KarakeepHandler(
                cfg=cfg,
                db=db,
                response_formatter=core.response_formatter,
                repository=karakeep_sync_repo,
            ),
            "listen": ListenHandler(
                cfg=cfg,
                db=db,
                response_formatter=core.response_formatter,
                tts_service_factory=lambda: TTSService(
                    summary_repository=summary_repo,
                    audio_generation_repository=SqliteAudioGenerationRepositoryAdapter(db),
                    tts_provider=ElevenLabsTTSProviderAdapter(cfg.tts),
                    audio_storage=FileSystemAudioStorageAdapter(cfg.tts.audio_storage_path),
                    voice_id=cfg.tts.voice_id,
                    model_name=cfg.tts.model,
                    max_chars_per_request=cfg.tts.max_chars_per_request,
                ),
            ),
        },
    )
    command_dispatcher = TelegramCommandDispatcher(
        cfg=cfg,
        response_formatter=dispatcher_deps.response_formatter,
        db=db,
        url_processor=dispatcher_deps.url_processor,
        audit_func=dispatcher_deps.audit_func,
        url_handler=dispatcher_deps.url_handler,
        topic_searcher=dispatcher_deps.topic_searcher,
        local_searcher=dispatcher_deps.local_searcher,
        task_manager=dispatcher_deps.task_manager,
        hybrid_search=dispatcher_deps.hybrid_search,
        verbosity_resolver=dispatcher_deps.verbosity_resolver,
        user_repo=telegram_repositories.user_repository,
        summary_repo=telegram_repositories.summary_repository,
        request_repo=telegram_repositories.request_repository,
        llm_repo=telegram_repositories.llm_repository,
        application_services=dispatcher_deps.application_services,
        handlers=dispatcher_deps.handlers,
    )
    access_controller = AccessController(
        cfg=cfg,
        db=db,
        response_formatter=core.response_formatter,
        audit_func=audit_sink,
        user_repo=user_repo,
    )
    _lang = getattr(core.response_formatter, "_lang", "en")
    callback_handler = CallbackHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_handler=url_handler,
        hybrid_search=search.hybrid_search_service,
        lang=_lang,
    )
    message_router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=access_controller,
        command_processor=command_dispatcher,
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=core.response_formatter,
        audit_func=audit_sink,
        task_manager=task_manager,
        attachment_processor=attachment_processor,
        user_repo=user_repo,
        callback_handler=callback_handler,
        lang=_lang,
    )
    message_handler = MessageHandler(
        cfg=cfg,
        db=db,
        audit_repo=audit_repo,
        task_manager=task_manager,
        access_controller=access_controller,
        url_handler=url_handler,
        command_dispatcher=command_dispatcher,
        callback_handler=callback_handler,
        message_router=message_router,
        url_processor=url_processor,
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
        telegram_client=telegram_client,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        forward_processor=forward_processor,
        attachment_processor=attachment_processor,
        message_handler=message_handler,
        adaptive_timeout_service=adaptive_timeout_service,
        verbosity_resolver=verbosity_resolver,
    )


def build_summary_cli_runtime(
    cfg: AppConfig,
    db: DatabaseSessionManager,
) -> SummaryCliRuntime:
    """Build the CLI summary runtime using the same shared resources as Telegram."""
    audit_sink = build_async_audit_sink(db)
    core = build_core_dependencies(cfg, db, audit_sink=audit_sink)
    search = build_search_dependencies(
        cfg,
        db,
        llm_client=core.llm_client,
        audit_func=core.audit_sink,
        firecrawl_client=core.firecrawl_client,
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
    )
    application_services = build_application_services(
        db,
        topic_search_service=search.local_searcher,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )
    user_repo = build_user_repository(db)
    summary_repo = build_summary_repository(db)
    request_repo = build_request_repository(db)
    llm_repo = build_llm_repository(db)
    karakeep_sync_repo = build_karakeep_sync_repository(db)
    url_handler = URLHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        user_repo=user_repo,
        request_repo=request_repo,
    )
    command_processor = TelegramCommandDispatcher(
        cfg=cfg,
        response_formatter=core.response_formatter,
        db=db,
        url_processor=url_processor,
        audit_func=core.audit_sink,
        url_handler=url_handler,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        user_repo=user_repo,
        summary_repo=summary_repo,
        request_repo=request_repo,
        llm_repo=llm_repo,
        application_services=application_services,
        handlers={
            "karakeep": KarakeepHandler(
                cfg=cfg,
                db=db,
                response_formatter=core.response_formatter,
                repository=karakeep_sync_repo,
            ),
            "listen": ListenHandler(
                cfg=cfg,
                db=db,
                response_formatter=core.response_formatter,
                tts_service_factory=lambda: TTSService(
                    summary_repository=summary_repo,
                    audio_generation_repository=SqliteAudioGenerationRepositoryAdapter(db),
                    tts_provider=ElevenLabsTTSProviderAdapter(cfg.tts),
                    audio_storage=FileSystemAudioStorageAdapter(cfg.tts.audio_storage_path),
                    voice_id=cfg.tts.voice_id,
                    model_name=cfg.tts.model,
                    max_chars_per_request=cfg.tts.max_chars_per_request,
                ),
            ),
        },
    )
    return SummaryCliRuntime(
        core=core,
        search=search,
        application_services=application_services,
        url_processor=url_processor,
        command_processor=command_processor,
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
            extra={"error": str(exc)},
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
            extra={"error": str(exc)},
        )
