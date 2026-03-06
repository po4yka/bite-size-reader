from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.attachment.attachment_processor import AttachmentProcessor
from app.adapters.content.scraper.factory import ContentScraperFactory
from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.llm import LLMClientFactory, LLMClientProtocol
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.telegram.telegram_client import TelegramClient
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.adaptive_timeout import AdaptiveTimeoutService
from app.services.chroma_vector_search_service import ChromaVectorSearchService
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_search_service import HybridSearchService
from app.services.query_expansion_service import QueryExpansionService
from app.services.reranking_service import OpenRouterRerankingService
from app.services.summary_embedding_generator import SummaryEmbeddingGenerator
from app.services.topic_search import LocalTopicSearchService, TopicSearchService

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable

    from app.adapters.content.scraper.chain import ContentScraperChain
    from app.adapters.telegram.telegram_bot import TelegramBot
    from app.config import AppConfig
    from app.core.verbosity import VerbosityResolver
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_SEARCH_MAX_RESULTS = 5


@dataclass
class ExternalClients:
    """Container for external service clients."""

    firecrawl: FirecrawlClient | None
    llm_client: LLMClientProtocol
    scraper_chain: ContentScraperChain | None = None


@dataclass
class BotComponents:
    """Container for bot components and services."""

    telegram_client: TelegramClient
    response_formatter: ResponseFormatter
    url_processor: URLProcessor
    forward_processor: ForwardProcessor
    attachment_processor: AttachmentProcessor
    message_handler: MessageHandler
    topic_searcher: TopicSearchService
    local_searcher: LocalTopicSearchService
    embedding_service: EmbeddingService
    chroma_vector_search_service: ChromaVectorSearchService
    query_expansion_service: QueryExpansionService
    hybrid_search_service: HybridSearchService
    vector_store: ChromaVectorStore
    adaptive_timeout_service: AdaptiveTimeoutService | None = None
    verbosity_resolver: VerbosityResolver | None = None
    container: Any | None = None


class BotFactory:
    """Factory for creating TelegramBot instances with all dependencies."""

    @staticmethod
    def create_external_clients(
        cfg: AppConfig,
        audit_func: Callable[[str, str, dict], None],
    ) -> ExternalClients:
        """Create external service clients (Firecrawl, LLM client).

        The LLM client is created based on the LLM_PROVIDER config setting,
        which can be "openrouter", "openai", or "anthropic".
        """
        firecrawl: FirecrawlClient | None = None
        if cfg.firecrawl.api_key:
            firecrawl = FirecrawlClient(
                api_key=cfg.firecrawl.api_key,
                timeout_sec=cfg.firecrawl.timeout_sec,
                audit=audit_func,
                debug_payloads=cfg.runtime.debug_payloads,
                log_truncate_length=cfg.runtime.log_truncate_length,
                max_connections=cfg.firecrawl.max_connections,
                max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
                keepalive_expiry=cfg.firecrawl.keepalive_expiry,
                credit_warning_threshold=cfg.firecrawl.credit_warning_threshold,
                credit_critical_threshold=cfg.firecrawl.credit_critical_threshold,
                max_response_size_mb=cfg.firecrawl.max_response_size_mb,
                max_age_seconds=cfg.firecrawl.max_age_seconds,
                remove_base64_images=cfg.firecrawl.remove_base64_images,
                block_ads=cfg.firecrawl.block_ads,
                skip_tls_verification=cfg.firecrawl.skip_tls_verification,
                include_markdown_format=cfg.firecrawl.include_markdown_format,
                include_html_format=cfg.firecrawl.include_html_format,
                include_links_format=cfg.firecrawl.include_links_format,
                include_summary_format=cfg.firecrawl.include_summary_format,
                include_images_format=cfg.firecrawl.include_images_format,
                enable_screenshot_format=cfg.firecrawl.enable_screenshot_format,
                screenshot_full_page=cfg.firecrawl.screenshot_full_page,
                screenshot_quality=cfg.firecrawl.screenshot_quality,
                screenshot_viewport_width=cfg.firecrawl.screenshot_viewport_width,
                screenshot_viewport_height=cfg.firecrawl.screenshot_viewport_height,
                json_prompt=cfg.firecrawl.json_prompt,
                json_schema=cfg.firecrawl.json_schema,
                wait_for_ms=cfg.firecrawl.wait_for_ms,
            )

        # Create LLM client using factory based on LLM_PROVIDER config
        llm_client = LLMClientFactory.create_from_config(cfg, audit=audit_func)

        # Create multi-provider scraper chain for content extraction
        scraper_chain = ContentScraperFactory.create_from_config(cfg, audit=audit_func)

        return ExternalClients(
            firecrawl=firecrawl, llm_client=llm_client, scraper_chain=scraper_chain
        )

    @staticmethod
    def create_components(
        cfg: AppConfig,
        db: DatabaseSessionManager,
        clients: ExternalClients,
        audit_func: Callable[[str, str, dict], None],
        safe_reply_func: Callable,
        reply_json_func: Callable,
        sem_func: Callable[[], asyncio.Semaphore],
        db_write_queue: DbWriteQueue | None = None,
    ) -> BotComponents:
        """Create all bot components and wire them together."""
        from app.core.verbosity import VerbosityResolver
        from app.infrastructure.persistence.sqlite.repositories.user_repository import (
            SqliteUserRepositoryAdapter,
        )

        user_repo = SqliteUserRepositoryAdapter(db)
        verbosity_resolver = VerbosityResolver(user_repo)

        # Resolve UI language from config
        ui_lang = cfg.runtime.preferred_lang
        if ui_lang == "auto":
            ui_lang = "en"

        response_formatter = BotFactory._create_response_formatter(
            cfg=cfg,
            safe_reply_func=safe_reply_func,
            reply_json_func=reply_json_func,
            verbosity_resolver=verbosity_resolver,
            ui_lang=ui_lang,
        )

        topic_search_max_results = BotFactory._get_topic_search_limit(cfg)

        topic_searcher = BotFactory._create_topic_searcher(
            clients=clients,
            topic_search_max_results=topic_search_max_results,
            audit_func=audit_func,
        )
        (
            url_processor,
            forward_processor,
            attachment_processor,
        ) = BotFactory._build_processing_components(
            cfg=cfg,
            db=db,
            clients=clients,
            response_formatter=response_formatter,
            topic_searcher=topic_searcher,
            audit_func=audit_func,
            sem_func=sem_func,
            db_write_queue=db_write_queue,
        )

        search_stack = BotFactory._build_search_stack(
            cfg=cfg,
            db=db,
            clients=clients,
            audit_func=audit_func,
            topic_search_max_results=topic_search_max_results,
        )
        vector_store = search_stack["vector_store"]
        local_searcher = search_stack["local_searcher"]
        embedding_service = search_stack["embedding_service"]
        embedding_generator = search_stack["embedding_generator"]
        query_expansion_service = search_stack["query_expansion_service"]
        chroma_vector_search_service = search_stack["chroma_vector_search_service"]
        hybrid_search_service = search_stack["hybrid_search_service"]

        from app.di.container import Container

        container = Container(
            database=db,
            topic_search_service=local_searcher,
            analytics_service=None,  # No analytics service yet
            vector_store=vector_store,
            embedding_generator=embedding_generator,
        )
        # Wire event handlers automatically
        container.wire_event_handlers_auto()

        logger.info(
            "hexagonal_architecture_initialized",
            extra={
                "event_bus_handlers": container.event_bus().get_handler_count(
                    type("DomainEvent", (), {})  # Base event type
                ),
            },
        )

        # Create telegram client
        telegram_client = TelegramClient(cfg=cfg)

        # Wire response formatter to telegram client
        response_formatter._telegram_client = telegram_client

        BotFactory._configure_forum_topics(
            cfg=cfg,
            response_formatter=response_formatter,
            telegram_client=telegram_client,
        )
        adaptive_timeout_service = BotFactory._create_adaptive_timeout_service(cfg=cfg, db=db)

        # Create message handler (will be wired with URL processor entrypoint by TelegramBot)
        message_handler = MessageHandler(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            url_processor=url_processor,  # Will be replaced with entrypoint by TelegramBot
            forward_processor=forward_processor,
            topic_searcher=topic_searcher,
            local_searcher=local_searcher,
            container=container,
            hybrid_search=hybrid_search_service,
            attachment_processor=attachment_processor,
            verbosity_resolver=verbosity_resolver,
            adaptive_timeout_service=adaptive_timeout_service,
        )

        return BotComponents(
            telegram_client=telegram_client,
            response_formatter=response_formatter,
            url_processor=url_processor,
            forward_processor=forward_processor,
            attachment_processor=attachment_processor,
            message_handler=message_handler,
            topic_searcher=topic_searcher,
            local_searcher=local_searcher,
            embedding_service=embedding_service,
            chroma_vector_search_service=chroma_vector_search_service,
            query_expansion_service=query_expansion_service,
            hybrid_search_service=hybrid_search_service,
            vector_store=vector_store,
            adaptive_timeout_service=adaptive_timeout_service,
            verbosity_resolver=verbosity_resolver,
            container=container,
        )

    @staticmethod
    def create_bot(cfg: AppConfig, db: DatabaseSessionManager) -> TelegramBot:
        """Create a fully initialized TelegramBot instance.

        This is the main entry point for creating a bot with all dependencies.
        """
        # Import here to avoid circular dependency
        from app.adapters.telegram.telegram_bot import TelegramBot

        return TelegramBot(cfg=cfg, db=db)

    @staticmethod
    def _get_topic_search_limit(cfg: AppConfig) -> int:
        """Return a sanitized topic search limit from runtime config."""
        raw_value = cfg.runtime.topic_search_max_results

        try:
            limit = int(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "topic_search_limit_invalid",
                extra={"value": raw_value},
            )
            return DEFAULT_TOPIC_SEARCH_MAX_RESULTS

        if limit <= 0:
            logger.warning(
                "topic_search_limit_non_positive",
                extra={"value": limit},
            )
            return DEFAULT_TOPIC_SEARCH_MAX_RESULTS

        if limit > 10:
            logger.warning(
                "topic_search_limit_too_large",
                extra={"value": limit},
            )
            return 10

        return limit

    @staticmethod
    def _build_search_stack(
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        clients: ExternalClients,
        audit_func: Callable[[str, str, dict], None],
        topic_search_max_results: int,
    ) -> dict[str, Any]:
        vector_store: ChromaVectorStore | None = None
        try:
            vector_store = ChromaVectorStore(
                host=cfg.vector_store.host,
                auth_token=cfg.vector_store.auth_token,
                environment=cfg.vector_store.environment,
                user_scope=cfg.vector_store.user_scope,
                collection_version=cfg.vector_store.collection_version,
                required=cfg.vector_store.required,
                connection_timeout=cfg.vector_store.connection_timeout,
            )
            if not vector_store.available:
                logger.warning(
                    "chroma_not_available_continuing",
                    extra={"host": cfg.vector_store.host},
                )
        except Exception as e:
            logger.warning(
                "chroma_init_failed_continuing_without_vector_search",
                extra={"error": str(e), "host": cfg.vector_store.host},
            )
            vector_store = None

        local_searcher = LocalTopicSearchService(
            db=db,
            max_results=topic_search_max_results,
            audit_func=audit_func,
        )
        embedding_service = EmbeddingService()
        embedding_generator = SummaryEmbeddingGenerator(db=db, embedding_service=embedding_service)
        query_expansion_service = QueryExpansionService(max_expansions=5, use_synonyms=True)

        chroma_vector_search_service: ChromaVectorSearchService | None = None
        if vector_store is not None:
            chroma_vector_search_service = ChromaVectorSearchService(
                vector_store=vector_store,
                embedding_service=embedding_service,
                default_top_k=topic_search_max_results * 2,
            )

        reranking_service = OpenRouterRerankingService(
            client=clients.llm_client,
            top_k=topic_search_max_results * 2,
            timeout_sec=cfg.runtime.request_timeout_sec,
        )
        hybrid_search_service = HybridSearchService(
            fts_service=local_searcher,
            vector_service=chroma_vector_search_service,
            fts_weight=1.0 if chroma_vector_search_service is None else 0.4,
            vector_weight=0.0 if chroma_vector_search_service is None else 0.6,
            max_results=topic_search_max_results,
            query_expansion=query_expansion_service,
            reranking=reranking_service,
        )
        return {
            "vector_store": vector_store,
            "local_searcher": local_searcher,
            "embedding_service": embedding_service,
            "embedding_generator": embedding_generator,
            "query_expansion_service": query_expansion_service,
            "chroma_vector_search_service": chroma_vector_search_service,
            "hybrid_search_service": hybrid_search_service,
        }

    @staticmethod
    def _configure_forum_topics(
        *,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        telegram_client: TelegramClient,
    ) -> None:
        if not cfg.telegram.forum_topics_enabled:
            return
        from app.adapters.telegram.topic_manager import TopicManager

        topic_manager = TopicManager()
        response_formatter._summary_presenter._topic_manager = topic_manager
        telegram_client.topic_manager = topic_manager
        logger.info("forum_topic_manager_initialized")

    @staticmethod
    def _create_adaptive_timeout_service(
        *, cfg: AppConfig, db: DatabaseSessionManager
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
        except Exception as e:
            logger.warning(
                "adaptive_timeout_service_init_failed",
                extra={"error": str(e)},
            )
            return None

    @staticmethod
    def _create_response_formatter(
        *,
        cfg: AppConfig,
        safe_reply_func: Callable,
        reply_json_func: Callable,
        verbosity_resolver: VerbosityResolver,
        ui_lang: str,
    ) -> ResponseFormatter:
        return ResponseFormatter(
            safe_reply_func=safe_reply_func,
            reply_json_func=reply_json_func,
            telegram_limits=cfg.telegram_limits,
            telegram_config=cfg.telegram,
            verbosity_resolver=verbosity_resolver,
            admin_log_chat_id=cfg.telegram.admin_log_chat_id,
            lang=ui_lang,
        )

    @staticmethod
    def _create_topic_searcher(
        *,
        clients: ExternalClients,
        topic_search_max_results: int,
        audit_func: Callable[[str, str, dict], None],
    ) -> TopicSearchService | None:
        if clients.firecrawl is None:
            return None
        return TopicSearchService(
            firecrawl=clients.firecrawl,
            max_results=topic_search_max_results,
            audit_func=audit_func,
        )

    @staticmethod
    def _build_processing_components(
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        clients: ExternalClients,
        response_formatter: ResponseFormatter,
        topic_searcher: TopicSearchService | None,
        audit_func: Callable[[str, str, dict], None],
        sem_func: Callable[[], asyncio.Semaphore],
        db_write_queue: DbWriteQueue | None,
    ) -> tuple[URLProcessor, ForwardProcessor, AttachmentProcessor]:
        url_processor = URLProcessor(
            cfg=cfg,
            db=db,
            firecrawl=clients.scraper_chain,
            openrouter=clients.llm_client,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem_func,
            topic_search=topic_searcher if cfg.web_search.enabled else None,
            db_write_queue=db_write_queue,
        )
        forward_processor = ForwardProcessor(
            cfg=cfg,
            db=db,
            openrouter=clients.llm_client,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem_func,
            db_write_queue=db_write_queue,
        )
        attachment_processor = AttachmentProcessor(
            cfg=cfg,
            db=db,
            openrouter=clients.llm_client,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem_func,
            db_write_queue=db_write_queue,
        )
        return url_processor, forward_processor, attachment_processor
