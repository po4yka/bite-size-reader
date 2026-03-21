"""Shared runtime and dependency composition for summarization services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import LLMResponseWorkflow
from app.adapters.content.llm_summarizer_articles import LLMArticleGenerator
from app.adapters.content.llm_summarizer_cache import LLMSummaryCache
from app.adapters.content.llm_summarizer_insights import (
    LLMInsightsGenerator,
    insights_has_content,
)
from app.adapters.content.llm_summarizer_metadata import LLMSummaryMetadataHelper
from app.adapters.content.llm_summarizer_semantic import LLMSemanticHelper
from app.adapters.content.llm_summarizer_text import coerce_string_list, truncate_content_text
from app.adapters.content.search_context_enricher import SearchContextEnricher
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.application.ports import (
        CrawlResultRepositoryPort,
        RequestRepositoryPort,
        SummaryRepositoryPort,
    )
    from app.application.services.topic_search import TopicSearchService
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue


class SummarizationRuntime:
    """Composition root for shared summarization infrastructure."""

    def __init__(
        self,
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict[str, Any]], None],
        sem: Callable[[], Any],
        topic_search: TopicSearchService | None = None,
        db_write_queue: DbWriteQueue | None = None,
        summary_repo: SummaryRepositoryPort | None = None,
        request_repo: RequestRepositoryPort | None = None,
        crawl_result_repo: CrawlResultRepositoryPort | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self.audit = audit_func
        self.sem = sem
        self.topic_search = topic_search
        self.db_write_queue = db_write_queue

        if summary_repo is None:
            summary_repo = SqliteSummaryRepositoryAdapter(db)
        if request_repo is None:
            request_repo = SqliteRequestRepositoryAdapter(db)
        if crawl_result_repo is None:
            crawl_result_repo = SqliteCrawlResultRepositoryAdapter(db)
        self.summary_repo = summary_repo
        self.request_repo = request_repo
        self.crawl_result_repo = crawl_result_repo

        self.workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            db_write_queue=db_write_queue,
        )
        self.cache = RedisCache(cfg)
        self.prompt_version = cfg.runtime.summary_prompt_version
        self.semantic_helper = LLMSemanticHelper()
        self.cache_helper = LLMSummaryCache(
            cache=self.cache,
            cfg=cfg,
            prompt_version=self.prompt_version,
            insights_has_content=insights_has_content,
        )
        self.insights_generator = LLMInsightsGenerator(
            cfg=cfg,
            openrouter=openrouter,
            workflow=self.workflow,
            summary_repo=self.summary_repo,
            cache_helper=self.cache_helper,
            sem=sem,
            coerce_string_list=coerce_string_list,
            truncate_content_text=truncate_content_text,
        )
        self.metadata_helper = LLMSummaryMetadataHelper(
            request_repo=self.request_repo,
            crawl_result_repo=self.crawl_result_repo,
            openrouter=openrouter,
            workflow=self.workflow,
            sem=sem,
            semantic_helper=self.semantic_helper,
        )
        self.article_generator = LLMArticleGenerator(
            cfg=cfg,
            openrouter=openrouter,
            workflow=self.workflow,
            cache_helper=self.cache_helper,
            sem=sem,
            select_max_tokens=self.insights_generator.select_max_tokens,
            coerce_string_list=coerce_string_list,
        )
        self.search_enricher = SearchContextEnricher(
            cfg=cfg,
            openrouter=openrouter,
            topic_search=topic_search,
        )

    async def aclose(self, timeout: float = 5.0) -> None:
        """Drain background workflow tasks."""
        await self.workflow.aclose(timeout=timeout)
