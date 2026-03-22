from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.attachment.attachment_processor import AttachmentProcessor
from app.adapters.telegram.access_controller import AccessController
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.command_dispatch import (
    AliasCommandRoute,
    CommandContextFactory,
    TelegramCommandRoutes,
    TelegramCommandRuntimeState,
    TextCommandRoute,
    UidCommandRoute,
)
from app.adapters.telegram.command_dispatcher import TelegramCommandDispatcher
from app.adapters.telegram.command_handlers.admin_handler import AdminHandler
from app.adapters.telegram.command_handlers.backup_handler import BackupHandler
from app.adapters.telegram.command_handlers.content_handler import ContentHandler
from app.adapters.telegram.command_handlers.digest_handler import DigestHandler
from app.adapters.telegram.command_handlers.export_command import ExportHandler
from app.adapters.telegram.command_handlers.init_session_handler import InitSessionHandler
from app.adapters.telegram.command_handlers.listen_handler import ListenHandler
from app.adapters.telegram.command_handlers.onboarding_handler import OnboardingHandler
from app.adapters.telegram.command_handlers.rules_handler import RulesHandler
from app.adapters.telegram.command_handlers.search_handler import SearchHandler
from app.adapters.telegram.command_handlers.settings_handler import SettingsHandler
from app.adapters.telegram.command_handlers.tag_handler import TagHandler
from app.adapters.telegram.command_handlers.url_commands_handler import URLCommandsHandler
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
    telegram_repositories = TelegramRepositories(
        user_repository=user_repo,
        summary_repository=summary_repo,
        request_repository=request_repo,
        llm_repository=llm_repo,
        audit_log_repository=audit_repo,
        batch_session_repository=batch_session_repo,
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
    dispatcher_deps = _build_command_dispatcher_deps(
        cfg=cfg,
        db=db,
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
        tts_service_factory=lambda: TTSService(
            summary_repository=summary_repo,
            audio_generation_repository=SqliteAudioGenerationRepositoryAdapter(db),
            tts_provider=ElevenLabsTTSProviderAdapter(cfg.tts),
            audio_storage=FileSystemAudioStorageAdapter(cfg.tts.audio_storage_path),
            voice_id=cfg.tts.voice_id,
            model_name=cfg.tts.model,
            max_chars_per_request=cfg.tts.max_chars_per_request,
        ),
    )
    command_dispatcher = TelegramCommandDispatcher(
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
    url_handler = URLHandler(
        db=db,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        user_repo=user_repo,
        request_repo=request_repo,
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
        repositories=TelegramRepositories(
            user_repository=user_repo,
            summary_repository=summary_repo,
            request_repository=request_repo,
            llm_repository=llm_repo,
            audit_log_repository=None,
            batch_session_repository=None,
        ),
        tts_service_factory=lambda: TTSService(
            summary_repository=summary_repo,
            audio_generation_repository=SqliteAudioGenerationRepositoryAdapter(db),
            tts_provider=ElevenLabsTTSProviderAdapter(cfg.tts),
            audio_storage=FileSystemAudioStorageAdapter(cfg.tts.audio_storage_path),
            voice_id=cfg.tts.voice_id,
            model_name=cfg.tts.model,
            max_chars_per_request=cfg.tts.max_chars_per_request,
        ),
    )
    command_processor = TelegramCommandDispatcher(
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
    return SummaryCliRuntime(
        core=core,
        search=search,
        application_services=application_services,
        url_processor=url_processor,
        command_processor=command_processor,
    )


def _build_command_dispatcher_deps(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    response_formatter: Any,
    audit_func: Any,
    url_processor: URLProcessor,
    url_handler: URLHandler | None,
    topic_searcher: Any | None,
    local_searcher: Any | None,
    task_manager: UserTaskManager | None,
    hybrid_search: Any | None,
    verbosity_resolver: Any | None,
    application_services: Any | None,
    repositories: TelegramRepositories,
    tts_service_factory: Any | None,
) -> TelegramCommandDispatcherDeps:
    runtime_state = TelegramCommandRuntimeState(
        url_processor=url_processor,
        url_handler=url_handler,
        topic_searcher=topic_searcher,
        local_searcher=local_searcher,
        _task_manager=task_manager,
        hybrid_search=hybrid_search,
    )
    context_factory = CommandContextFactory(
        user_repo=repositories.user_repository,
        response_formatter=response_formatter,
        audit_func=audit_func,
    )

    onboarding_handler = OnboardingHandler(response_formatter)
    admin_handler = AdminHandler(
        db=db,
        response_formatter=response_formatter,
        url_processor=url_processor,
        url_handler=url_handler,
    )
    url_commands_handler = URLCommandsHandler(
        response_formatter=response_formatter,
        processor_provider=runtime_state,
    )
    content_handler = ContentHandler(
        response_formatter=response_formatter,
        summary_repo=repositories.summary_repository,
        llm_repo=repositories.llm_repository,
        unread_summaries_use_case=getattr(application_services, "unread_summaries", None),
        mark_summary_as_read_use_case=getattr(application_services, "mark_summary_as_read", None),
        event_bus=getattr(application_services, "event_bus", None),
    )
    search_handler = SearchHandler(
        response_formatter=response_formatter,
        searcher_provider=runtime_state,
        search_topics_use_case=getattr(application_services, "search_topics", None),
    )
    listen_handler = ListenHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
        tts_service_factory=tts_service_factory,
    )
    digest_handler = DigestHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
    )
    init_session_handler = InitSessionHandler(
        cfg=cfg,
        response_formatter=response_formatter,
    )
    settings_handler = SettingsHandler(
        verbosity_resolver=verbosity_resolver,
        cfg=cfg,
    )
    tag_handler = TagHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
    )
    rules_handler = RulesHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
    )
    export_handler = ExportHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
    )
    backup_handler = BackupHandler(
        cfg=cfg,
        db=db,
        response_formatter=response_formatter,
    )

    def build_uid_handler(handler_method: Any) -> Any:
        async def _handler(
            message: Any,
            uid: int,
            correlation_id: str,
            interaction_id: int,
            start_time: float,
        ) -> None:
            ctx = context_factory.build(
                message=message,
                uid=uid,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                start_time=start_time,
            )
            await handler_method(ctx)

        return _handler

    def build_text_handler(handler_method: Any) -> Any:
        async def _handler(
            message: Any,
            text: str,
            uid: int,
            correlation_id: str,
            interaction_id: int,
            start_time: float,
        ) -> None:
            ctx = context_factory.build(
                message=message,
                text=text,
                uid=uid,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                start_time=start_time,
            )
            await handler_method(ctx)

        return _handler

    def build_alias_handler(handler_method: Any) -> Any:
        async def _handler(
            message: Any,
            text: str,
            uid: int,
            correlation_id: str,
            interaction_id: int,
            start_time: float,
            command: str,
        ) -> None:
            ctx = context_factory.build(
                message=message,
                text=text,
                uid=uid,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                start_time=start_time,
            )
            await handler_method(ctx, command=command)

        return _handler

    routes = TelegramCommandRoutes(
        pre_alias_uid=(
            UidCommandRoute("/start", build_uid_handler(onboarding_handler.handle_start)),
            UidCommandRoute("/help", build_uid_handler(onboarding_handler.handle_help)),
            UidCommandRoute("/dbinfo", build_uid_handler(admin_handler.handle_dbinfo)),
            UidCommandRoute("/dbverify", build_uid_handler(admin_handler.handle_dbverify)),
            UidCommandRoute("/clearcache", build_uid_handler(admin_handler.handle_clearcache)),
        ),
        pre_alias_text=(
            TextCommandRoute("/admin", build_text_handler(admin_handler.handle_admin)),
        ),
        local_search_aliases=(
            AliasCommandRoute(
                ("/finddb", "/findlocal"),
                build_alias_handler(search_handler.handle_find_local),
            ),
        ),
        online_search_aliases=(
            AliasCommandRoute(
                ("/findweb", "/findonline", "/find"),
                build_alias_handler(search_handler.handle_find_online),
            ),
        ),
        pre_summarize_text=(
            TextCommandRoute(
                "/summarize_all",
                build_text_handler(url_commands_handler.handle_summarize_all),
            ),
        ),
        summarize_prefix="/summarize",
        post_summarize_uid=(
            UidCommandRoute("/cancel", build_uid_handler(url_commands_handler.handle_cancel)),
        ),
        post_summarize_text=(
            TextCommandRoute("/untag", build_text_handler(tag_handler.handle_untag)),
            TextCommandRoute("/tags", build_text_handler(tag_handler.handle_tags)),
            TextCommandRoute("/tag", build_text_handler(tag_handler.handle_tag)),
            TextCommandRoute("/unread", build_text_handler(content_handler.handle_unread)),
            TextCommandRoute("/read", build_text_handler(content_handler.handle_read)),
            TextCommandRoute("/search", build_text_handler(search_handler.handle_search)),
            TextCommandRoute("/listen", build_text_handler(listen_handler.handle_listen)),
            TextCommandRoute("/cdigest", build_text_handler(digest_handler.handle_cdigest)),
            TextCommandRoute("/digest", build_text_handler(digest_handler.handle_digest)),
            TextCommandRoute("/channels", build_text_handler(digest_handler.handle_channels)),
            TextCommandRoute("/subscribe", build_text_handler(digest_handler.handle_subscribe)),
            TextCommandRoute(
                "/unsubscribe",
                build_text_handler(digest_handler.handle_unsubscribe),
            ),
            TextCommandRoute(
                "/init_session",
                build_text_handler(init_session_handler.handle_init_session),
            ),
            TextCommandRoute("/settings", build_text_handler(settings_handler.handle_settings)),
            TextCommandRoute("/rules", build_text_handler(rules_handler.handle_rules)),
            TextCommandRoute("/export", build_text_handler(export_handler.handle_export)),
            TextCommandRoute("/backups", build_text_handler(backup_handler.handle_backups)),
            TextCommandRoute("/backup", build_text_handler(backup_handler.handle_backup)),
        ),
        tail_uid=(UidCommandRoute("/debug", build_uid_handler(settings_handler.handle_debug)),),
    )

    return TelegramCommandDispatcherDeps(
        routes=routes,
        runtime_state=runtime_state,
        context_factory=context_factory,
        onboarding_handler=onboarding_handler,
        admin_handler=admin_handler,
        url_commands_handler=url_commands_handler,
        content_handler=content_handler,
        search_handler=search_handler,
        listen_handler=listen_handler,
        digest_handler=digest_handler,
        init_session_handler=init_session_handler,
        settings_handler=settings_handler,
        tag_handler=tag_handler,
        rules_handler=rules_handler,
        export_handler=export_handler,
        backup_handler=backup_handler,
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
