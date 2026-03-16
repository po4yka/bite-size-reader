from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.attachment.attachment_processor import AttachmentProcessor
from app.adapters.repository_ports import create_batch_session_repository, create_user_repository
from app.adapters.telegram.command_processor import CommandProcessor
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.telegram.telegram_client import TelegramClient
from app.adapters.content.url_processor import URLProcessor
from app.core.verbosity import VerbosityResolver
from app.di.container import Container
from app.di.search import build_search_dependencies, get_topic_search_limit
from app.di.shared import build_async_audit_sink, build_core_dependencies
from app.di.types import SummaryCliRuntime, TelegramRuntime
from app.security.file_validation import SecureFileValidator
from app.services.adaptive_timeout import AdaptiveTimeoutService
from app.services.related_reads_service import RelatedReadsService
from app.services.vector_search_service import VectorSearchService

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = logging.getLogger(__name__)


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
    user_repo = create_user_repository(db)
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

    url_processor = URLProcessor(
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
    )
    attachment_processor = AttachmentProcessor(
        cfg=cfg,
        db=db,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        db_write_queue=db_write_queue,
    )

    _wire_related_reads(
        cfg=cfg,
        db=db,
        search=search,
        url_processor=url_processor,
        forward_processor=forward_processor,
    )

    container = Container(
        database=db,
        topic_search_service=search.local_searcher,
        analytics_service=None,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )
    container.wire_event_handlers_auto()

    telegram_client = TelegramClient(cfg=cfg)
    core.response_formatter._telegram_client = telegram_client
    _configure_forum_topics(
        cfg=cfg,
        response_formatter=core.response_formatter,
        telegram_client=telegram_client,
    )

    adaptive_timeout_service = _create_adaptive_timeout_service(cfg=cfg, db=db)
    batch_session_repo = create_batch_session_repository(db)
    message_handler = MessageHandler(
        cfg=cfg,
        db=db,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        forward_processor=forward_processor,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        container=container,
        hybrid_search=search.hybrid_search_service,
        attachment_processor=attachment_processor,
        verbosity_resolver=verbosity_resolver,
        adaptive_timeout_service=adaptive_timeout_service,
        llm_client=core.llm_client,
        batch_session_repo=batch_session_repo,
        batch_config=cfg.batch_analysis,
        file_validator=SecureFileValidator(max_file_size=10 * 1024 * 1024),
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
        telegram_client=telegram_client,
        response_formatter=core.response_formatter,
        url_processor=url_processor,
        forward_processor=forward_processor,
        attachment_processor=attachment_processor,
        message_handler=message_handler,
        adaptive_timeout_service=adaptive_timeout_service,
        verbosity_resolver=verbosity_resolver,
        container=container,
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

    url_processor = URLProcessor(
        cfg=cfg,
        db=db,
        firecrawl=core.scraper_chain,
        openrouter=core.llm_client,
        response_formatter=core.response_formatter,
        audit_func=core.audit_sink,
        sem=core.semaphore_factory,
        topic_search=search.topic_searcher if cfg.web_search.enabled else None,
    )
    container = Container(
        database=db,
        topic_search_service=search.local_searcher,
        vector_store=search.vector_store,
        embedding_generator=search.embedding_generator,
    )
    container.wire_event_handlers_auto()
    command_processor = CommandProcessor(
        cfg=cfg,
        response_formatter=core.response_formatter,
        db=db,
        url_processor=url_processor,
        audit_func=core.audit_sink,
        topic_searcher=search.topic_searcher,
        local_searcher=search.local_searcher,
        container=container,
    )
    return SummaryCliRuntime(
        core=core,
        search=search,
        url_processor=url_processor,
        command_processor=command_processor,
        container=container,
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
    response_formatter._summary_presenter._topic_manager = topic_manager
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
            session_manager=db,
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
            db=db,
            embedding_service=search.embedding_service,
            max_results=10,
            min_similarity=0.3,
        )
        related_reads_service = RelatedReadsService(
            vector_search_service,
            min_similarity=cfg.runtime.related_reads_min_similarity,
        )
        url_processor._related_reads_service = related_reads_service
        forward_processor._related_reads_service = related_reads_service
        logger.info("related_reads_service_initialized")
    except Exception as exc:
        logger.warning(
            "related_reads_service_init_failed",
            extra={"error": str(exc)},
        )
