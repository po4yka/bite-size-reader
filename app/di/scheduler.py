from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from app.di.repositories import (
    build_crawl_result_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_user_repository,
)
from app.di.types import SchedulerDependencies

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.formatting.protocols import (
        ResponseFormatterFacade as ResponseFormatter,
    )
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


def build_scheduler_dependencies(
    cfg: AppConfig,
    db: DatabaseSessionManager,
) -> SchedulerDependencies:
    """Build scheduler job factories without constructing jobs inline in the service."""
    rss_bot_factory = None
    rss_delivery_factory = None
    signal_worker_factory = None
    source_ingestion_runner_factory = None
    if cfg.rss.enabled:
        rss_bot_factory = lambda: _create_digest_bot_client(cfg)  # noqa: E731
        rss_delivery_factory = lambda: _create_rss_delivery_service(cfg, db)  # noqa: E731
    if cfg.rss.enabled or cfg.signal_ingestion.any_enabled:
        signal_worker_factory = lambda: _create_signal_ingestion_worker(cfg, db)  # noqa: E731
    if cfg.signal_ingestion.any_enabled:
        source_ingestion_runner_factory = lambda: _create_source_ingestion_runner(cfg, db)  # noqa: E731

    return SchedulerDependencies(
        digest_userbot_factory=lambda: _create_digest_userbot(cfg),
        digest_llm_factory=lambda: _create_digest_llm_client(cfg),
        digest_bot_client_factory=lambda: _create_digest_bot_client(cfg),
        digest_service_factory=lambda userbot, llm_client, send_message: _create_digest_service(
            cfg,
            userbot=userbot,
            llm_client=llm_client,
            send_message=send_message,
        ),
        rss_bot_client_factory=rss_bot_factory,
        rss_delivery_factory=rss_delivery_factory,
        signal_worker_factory=signal_worker_factory,
        source_ingestion_runner_factory=source_ingestion_runner_factory,
    )


def _create_digest_userbot(cfg: AppConfig) -> Any:
    from app.adapters.digest.userbot_client import UserbotClient

    return UserbotClient(cfg, Path("/data"))


def _create_digest_llm_client(cfg: AppConfig) -> Any:
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

    return OpenRouterClient(
        api_key=cfg.openrouter.api_key,
        model=cfg.openrouter.model,
        fallback_models=cfg.openrouter.fallback_models,
    )


def _create_digest_bot_client(cfg: AppConfig) -> Any:
    from pyrogram import Client as PyroClient

    return PyroClient(
        name="digest_bot_sender",
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
        bot_token=cfg.telegram.bot_token,
        in_memory=True,
    )


def _create_digest_service(
    cfg: AppConfig,
    *,
    userbot: Any,
    llm_client: Any,
    send_message: Callable[[int, str, Any | None], Awaitable[None]],
) -> Any:
    from app.adapters.digest.analyzer import DigestAnalyzer
    from app.adapters.digest.channel_reader import ChannelReader
    from app.adapters.digest.digest_service import DigestService
    from app.adapters.digest.formatter import DigestFormatter

    reader = ChannelReader(cfg, userbot)
    analyzer = DigestAnalyzer(cfg, llm_client)
    formatter = DigestFormatter()
    return DigestService(
        cfg=cfg,
        reader=reader,
        analyzer=analyzer,
        formatter=formatter,
        send_message_func=send_message,
    )


def _create_rss_delivery_service(cfg: AppConfig, db: DatabaseSessionManager) -> Any:
    from app.adapters.content.pure_summary_service import PureSummaryService
    from app.adapters.content.scraper.factory import ContentScraperFactory
    from app.adapters.content.summarization_runtime import SummarizationRuntime
    from app.adapters.external.response_formatter import (
        ResponseFormatter as TelegramResponseFormatter,
    )
    from app.adapters.openrouter.openrouter_client import OpenRouterClient
    from app.adapters.rss.rss_delivery_service import RSSDeliveryService
    from app.di.shared import LazySemaphoreFactory
    from app.infrastructure.persistence.sqlite.repositories.rss_feed_repository import (
        SqliteRSSFeedRepositoryAdapter,
    )
    from app.prompts.manager import get_prompt_manager

    llm_client = OpenRouterClient(
        api_key=cfg.openrouter.api_key,
        model=cfg.openrouter.model,
        fallback_models=cfg.openrouter.fallback_models,
    )
    response_formatter = cast(
        "ResponseFormatter",
        TelegramResponseFormatter(
            telegram_limits=cfg.telegram_limits,
            telegram_config=cfg.telegram,
        ),
    )
    sem_factory = LazySemaphoreFactory(cfg.runtime.max_concurrent_calls)
    runtime = SummarizationRuntime(
        cfg=cfg,
        db=db,
        openrouter=llm_client,
        response_formatter=response_formatter,
        audit_func=lambda *_a, **_kw: None,
        sem=sem_factory,
        summary_repo=build_summary_repository(db),
        request_repo=build_request_repository(db),
        crawl_result_repo=build_crawl_result_repository(db),
        llm_repo=build_llm_repository(db),
        user_repo=build_user_repository(db),
    )
    pure_service = PureSummaryService(runtime=runtime)
    prompt_mgr = get_prompt_manager()

    scraper_chain = None
    if cfg.rss.scrape_short_content:
        audit = lambda *_a, **_kw: None  # noqa: E731
        scraper_chain = ContentScraperFactory.create_from_config(cfg, audit=audit)

    return RSSDeliveryService(
        cfg=cfg.rss,
        pure_summary_service=pure_service,
        system_prompt_loader=lambda lang: prompt_mgr.get_system_prompt(
            lang, include_examples=True, num_examples=2
        ),
        rss_repository=SqliteRSSFeedRepositoryAdapter(db),
        scraper_chain=scraper_chain,
    )


def _create_signal_ingestion_worker(cfg: AppConfig, db: DatabaseSessionManager) -> Any:
    from app.application.services.signal_ingestion_worker import SignalIngestionWorker
    from app.application.services.signal_scoring import SignalScoringService
    from app.core.embedding_space import resolve_embedding_space_identifier
    from app.infrastructure.embedding.embedding_factory import create_embedding_service
    from app.infrastructure.persistence.sqlite.repositories.signal_source_repository import (
        SqliteSignalSourceRepositoryAdapter,
    )
    from app.infrastructure.search.chroma_topic_similarity import ChromaTopicSimilarityAdapter
    from app.infrastructure.vector.chroma_store import ChromaVectorStore

    embedding_service = create_embedding_service(cfg.embedding)
    vector_store = ChromaVectorStore(
        host=cfg.vector_store.host,
        auth_token=cfg.vector_store.auth_token,
        environment=cfg.vector_store.environment,
        user_scope=cfg.vector_store.user_scope,
        collection_version=cfg.vector_store.collection_version,
        embedding_space=resolve_embedding_space_identifier(cfg.embedding),
        required=cfg.vector_store.required,
        connection_timeout=cfg.vector_store.connection_timeout,
    )
    return SignalIngestionWorker(
        repository=SqliteSignalSourceRepositoryAdapter(db),
        scorer=SignalScoringService(
            topic_similarity=ChromaTopicSimilarityAdapter(
                vector_store=vector_store,
                embedding_service=embedding_service,
            )
        ),
    )


def _create_source_ingestion_runner(cfg: AppConfig, db: DatabaseSessionManager) -> Any:
    from app.adapters.ingestors.hn import HackerNewsIngester
    from app.adapters.ingestors.reddit import RedditIngester, RequestRateBudget
    from app.adapters.ingestors.runner import SourceIngestionRunner
    from app.adapters.ingestors.twitter import TwitterIngester, TwitterIngestionConfig
    from app.infrastructure.persistence.sqlite.repositories.signal_source_repository import (
        SqliteSignalSourceRepositoryAdapter,
    )

    ingestion_cfg = cfg.signal_ingestion
    ingesters: list[Any] = []
    reddit_rate_budget = RequestRateBudget(
        max_requests_per_minute=ingestion_cfg.reddit_requests_per_minute
    )
    if ingestion_cfg.enabled and ingestion_cfg.hn_enabled:
        ingesters.extend(
            HackerNewsIngester(
                feed=feed,
                limit=ingestion_cfg.max_items_per_source,
                enabled=True,
            )
            for feed in ingestion_cfg.hn_feed_names()
        )
    if ingestion_cfg.enabled and ingestion_cfg.reddit_enabled:
        ingesters.extend(
            RedditIngester(
                subreddit=subreddit,
                listing=ingestion_cfg.reddit_listing,
                limit=ingestion_cfg.max_items_per_source,
                enabled=True,
                rate_budget=reddit_rate_budget,
            )
            for subreddit in ingestion_cfg.reddit_names()
        )
    ingesters.append(
        TwitterIngester(
            TwitterIngestionConfig(
                enabled=ingestion_cfg.enabled and ingestion_cfg.twitter_enabled,
                ack_cost=ingestion_cfg.twitter_ack_cost,
            )
        )
    )
    return SourceIngestionRunner(
        repository=SqliteSignalSourceRepositoryAdapter(db),
        ingesters=ingesters,
        subscriber_user_ids=cfg.telegram.allowed_user_ids,
    )
