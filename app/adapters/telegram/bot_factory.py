from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.telegram.telegram_client import TelegramClient
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_search_service import HybridSearchService
from app.services.query_expansion_service import QueryExpansionService
from app.services.summary_embedding_generator import SummaryEmbeddingGenerator
from app.services.topic_search import LocalTopicSearchService, TopicSearchService
from app.services.vector_search_service import VectorSearchService

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable

    from app.adapters.telegram.telegram_bot import TelegramBot
    from app.config import AppConfig
    from app.db.database import Database

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_SEARCH_MAX_RESULTS = 5


@dataclass
class ExternalClients:
    """Container for external service clients."""

    firecrawl: FirecrawlClient
    openrouter: OpenRouterClient


@dataclass
class BotComponents:
    """Container for bot components and services."""

    telegram_client: TelegramClient
    response_formatter: ResponseFormatter
    url_processor: URLProcessor
    forward_processor: ForwardProcessor
    message_handler: MessageHandler
    topic_searcher: TopicSearchService
    local_searcher: LocalTopicSearchService
    embedding_service: EmbeddingService
    vector_search_service: VectorSearchService
    query_expansion_service: QueryExpansionService
    hybrid_search_service: HybridSearchService
    vector_store: ChromaVectorStore
    container: Any | None = None


class BotFactory:
    """Factory for creating TelegramBot instances with all dependencies."""

    @staticmethod
    def create_external_clients(
        cfg: AppConfig,
        audit_func: Callable[[str, str, dict], None],
    ) -> ExternalClients:
        """Create external service clients (Firecrawl, OpenRouter)."""
        firecrawl = FirecrawlClient(
            api_key=cfg.firecrawl.api_key,
            timeout_sec=cfg.runtime.request_timeout_sec,
            audit=audit_func,
            debug_payloads=cfg.runtime.debug_payloads,
            log_truncate_length=cfg.runtime.log_truncate_length,
            max_connections=cfg.firecrawl.max_connections,
            max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
            keepalive_expiry=cfg.firecrawl.keepalive_expiry,
            credit_warning_threshold=cfg.firecrawl.credit_warning_threshold,
            credit_critical_threshold=cfg.firecrawl.credit_critical_threshold,
            max_response_size_mb=cfg.firecrawl.max_response_size_mb,
        )

        openrouter = OpenRouterClient(
            api_key=cfg.openrouter.api_key,
            model=cfg.openrouter.model,
            fallback_models=list(cfg.openrouter.fallback_models),
            http_referer=cfg.openrouter.http_referer,
            x_title=cfg.openrouter.x_title,
            timeout_sec=cfg.runtime.request_timeout_sec,
            audit=audit_func,
            debug_payloads=cfg.runtime.debug_payloads,
            provider_order=list(cfg.openrouter.provider_order),
            enable_stats=cfg.openrouter.enable_stats,
            log_truncate_length=cfg.runtime.log_truncate_length,
            enable_structured_outputs=cfg.openrouter.enable_structured_outputs,
            structured_output_mode=cfg.openrouter.structured_output_mode,
            require_parameters=cfg.openrouter.require_parameters,
            auto_fallback_structured=cfg.openrouter.auto_fallback_structured,
            max_response_size_mb=cfg.openrouter.max_response_size_mb,
        )

        return ExternalClients(firecrawl=firecrawl, openrouter=openrouter)

    @staticmethod
    def create_components(
        cfg: AppConfig,
        db: Database,
        clients: ExternalClients,
        audit_func: Callable[[str, str, dict], None],
        safe_reply_func: Callable,
        reply_json_func: Callable,
        sem_func: Callable[[], asyncio.Semaphore],
    ) -> BotComponents:
        """Create all bot components and wire them together."""
        # Create response formatter (will be wired to telegram_client later)
        response_formatter = ResponseFormatter(
            safe_reply_func=safe_reply_func,
            reply_json_func=reply_json_func,
            telegram_limits=cfg.telegram_limits,
        )

        # Create URL processor
        url_processor = URLProcessor(
            cfg=cfg,
            db=db,
            firecrawl=clients.firecrawl,
            openrouter=clients.openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem_func,
        )

        # Create forward processor
        forward_processor = ForwardProcessor(
            cfg=cfg,
            db=db,
            openrouter=clients.openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem_func,
        )

        # Determine topic search limit
        topic_search_max_results = BotFactory._get_topic_search_limit(cfg)

        # Initialize vector store
        vector_store = ChromaVectorStore(
            host=cfg.vector_store.host,
            auth_token=cfg.vector_store.auth_token,
            environment=cfg.vector_store.environment,
            user_scope=cfg.vector_store.user_scope,
            collection_version=cfg.vector_store.collection_version,
        )

        # Create search services
        topic_searcher = TopicSearchService(
            firecrawl=clients.firecrawl,
            max_results=topic_search_max_results,
            audit_func=audit_func,
        )

        local_searcher = LocalTopicSearchService(
            db=db,
            max_results=topic_search_max_results,
            audit_func=audit_func,
        )

        # Create hybrid search services
        embedding_service = EmbeddingService()
        vector_search_service = VectorSearchService(
            db=db,
            embedding_service=embedding_service,
            max_results=topic_search_max_results,
            min_similarity=0.3,
        )
        embedding_generator = SummaryEmbeddingGenerator(db=db, embedding_service=embedding_service)
        query_expansion_service = QueryExpansionService(
            max_expansions=5,
            use_synonyms=True,
        )
        # Re-ranking is optional and slower, so disabled by default
        reranking_service = None
        hybrid_search_service = HybridSearchService(
            fts_service=local_searcher,
            vector_service=vector_search_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=topic_search_max_results,
            query_expansion=query_expansion_service,
            reranking=reranking_service,
        )

        # Optional hexagonal architecture container
        container = None
        if getattr(cfg.runtime, "enable_hex_container", False):
            from app.di.container import Container

            container = Container(
                database=db,
                topic_search_service=local_searcher,
                content_fetcher=clients.firecrawl,
                llm_client=clients.openrouter,
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
        )

        return BotComponents(
            telegram_client=telegram_client,
            response_formatter=response_formatter,
            url_processor=url_processor,
            forward_processor=forward_processor,
            message_handler=message_handler,
            topic_searcher=topic_searcher,
            local_searcher=local_searcher,
            embedding_service=embedding_service,
            vector_search_service=vector_search_service,
            query_expansion_service=query_expansion_service,
            hybrid_search_service=hybrid_search_service,
            vector_store=vector_store,
            container=container,
        )

    @staticmethod
    def create_bot(cfg: AppConfig, db: Database) -> TelegramBot:
        """Create a fully initialized TelegramBot instance.

        This is the main entry point for creating a bot with all dependencies.
        """
        # Import here to avoid circular dependency
        from app.adapters.telegram.telegram_bot import TelegramBot

        return TelegramBot(cfg=cfg, db=db)

    @staticmethod
    def _get_topic_search_limit(cfg: AppConfig) -> int:
        """Return a sanitized topic search limit from runtime config."""
        runtime = getattr(cfg, "runtime", None)
        raw_value = getattr(runtime, "topic_search_max_results", DEFAULT_TOPIC_SEARCH_MAX_RESULTS)

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
