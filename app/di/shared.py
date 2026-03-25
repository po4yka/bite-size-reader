from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from app.adapters.content.scraper.factory import ContentScraperFactory
from app.adapters.external.firecrawl.client import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.llm import LLMClientFactory
from app.core.logging_utils import get_logger
from app.di.repositories import (
    build_audit_log_repository,
    build_crawl_result_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_user_repository,
)
from app.di.types import CoreDependencies

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.application.ports.requests import RequestRepositoryPort
    from app.application.ports.summaries import SummaryRepositoryPort
    from app.application.services.related_reads_service import RelatedReadsService
    from app.application.services.topic_search import TopicSearchService
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = get_logger(__name__)


class LazySemaphoreFactory:
    """Lazy semaphore factory mirroring runtime bot behavior."""

    def __init__(self, permits: int) -> None:
        self._permits = max(1, permits)
        self._semaphore: asyncio.Semaphore | None = None

    def __call__(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._permits)
        return self._semaphore


def build_async_audit_sink(
    db: DatabaseSessionManager,
    *,
    task_registry: set[asyncio.Task[Any]] | None = None,
) -> Callable[[str, str, dict[str, Any]], None]:
    """Create an async fire-and-forget audit callback backed by the DB."""
    repo = build_audit_log_repository(db)

    def audit(level: str, event: str, details: dict[str, Any]) -> None:
        payload = details if isinstance(details, dict) else {"details": str(details)}

        async def _write() -> None:
            try:
                await repo.async_insert_audit_log(
                    log_level=level,
                    event_type=event,
                    details=payload,
                )
            except Exception as exc:
                logger.warning(
                    "audit_persist_failed",
                    extra={"event": event, "error": str(exc)},
                )

        try:
            task = asyncio.create_task(_write())
        except RuntimeError as exc:
            logger.debug("audit_task_schedule_skipped", extra={"error": str(exc)})
            return

        if task_registry is not None:
            task_registry.add(task)
            task.add_done_callback(task_registry.discard)

    return audit


def resolve_ui_lang(cfg: AppConfig) -> str:
    ui_lang = cfg.runtime.preferred_lang
    return "en" if ui_lang == "auto" else ui_lang


def build_core_dependencies(
    cfg: AppConfig,
    db: DatabaseSessionManager,
    *,
    audit_sink: Callable[[str, str, dict[str, Any]], None] | None = None,
    semaphore_factory: Callable[[], asyncio.Semaphore] | None = None,
    response_formatter_kwargs: dict[str, Any] | None = None,
) -> CoreDependencies:
    """Build the shared LLM, scraper, formatter, and concurrency resources."""
    audit = audit_sink or _default_audit
    sem_factory = semaphore_factory or LazySemaphoreFactory(cfg.runtime.max_concurrent_calls)
    firecrawl_client = _build_firecrawl_client(cfg, audit)
    llm_client = LLMClientFactory.create_from_config(cfg, audit=audit)
    scraper_chain = ContentScraperFactory.create_from_config(cfg, audit=audit)

    response_kwargs = dict(response_formatter_kwargs or {})
    response_formatter = ResponseFormatter(
        telegram_limits=cfg.telegram_limits,
        telegram_config=cfg.telegram,
        lang=resolve_ui_lang(cfg),
        **response_kwargs,
    )

    return CoreDependencies(
        cfg=cfg,
        db=db,
        audit_sink=audit,
        semaphore_factory=sem_factory,
        llm_client=llm_client,
        scraper_chain=scraper_chain,
        response_formatter=response_formatter,
        firecrawl_client=firecrawl_client,
    )


def build_url_processor(
    *,
    cfg: AppConfig,
    db: DatabaseSessionManager,
    firecrawl: Any,
    openrouter: Any,
    response_formatter: Any,
    audit_func: Callable[[str, str, dict[str, Any]], None],
    sem: Callable[[], asyncio.Semaphore],
    topic_search: TopicSearchService | None = None,
    db_write_queue: DbWriteQueue | None = None,
    request_repo: RequestRepositoryPort | None = None,
    summary_repo: SummaryRepositoryPort | None = None,
    crawl_result_repo: Any | None = None,
    llm_repo: Any | None = None,
    user_repo: Any | None = None,
    related_reads_service: RelatedReadsService | None = None,
) -> Any:
    """Build the shared URL processor graph for Telegram, API, and CLI runtimes."""
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.telegram.summary_draft_streaming import SummaryDraftStreamCoordinator

    request_repository = request_repo or build_request_repository(db)
    summary_repository = summary_repo or build_summary_repository(db)
    crawl_repository = crawl_result_repo or build_crawl_result_repository(db)
    llm_repository = llm_repo or build_llm_repository(db)
    user_repository = user_repo or build_user_repository(db)

    return URLProcessor(
        cfg=cfg,
        db=db,
        firecrawl=firecrawl,
        openrouter=openrouter,
        response_formatter=response_formatter,
        audit_func=audit_func,
        sem=sem,
        topic_search=topic_search,
        db_write_queue=db_write_queue,
        request_repo=request_repository,
        summary_repo=summary_repository,
        crawl_result_repo=crawl_repository,
        llm_repo=llm_repository,
        user_repo=user_repository,
        related_reads_service=related_reads_service,
        stream_coordinator_factory=SummaryDraftStreamCoordinator,
    )


async def close_runtime_resources(*resources: Any) -> None:
    """Close all runtime resources that expose async cleanup hooks."""
    for resource in resources:
        if resource is None:
            continue
        close = getattr(resource, "aclose", None)
        if close is None:
            continue
        with contextlib.suppress(Exception):
            await close()


def _build_firecrawl_client(
    cfg: AppConfig,
    audit: Callable[[str, str, dict[str, Any]], None],
) -> FirecrawlClient | None:
    if not cfg.firecrawl.api_key:
        return None

    return FirecrawlClient.from_config(
        cfg.firecrawl,
        audit=audit,
        debug_payloads=cfg.runtime.debug_payloads,
        log_truncate_length=cfg.runtime.log_truncate_length,
    )


def _default_audit(level: str, event: str, details: dict[str, Any]) -> None:
    log_level = logging.INFO if level == "info" else logging.ERROR
    logger.log(log_level, event, extra=details)
