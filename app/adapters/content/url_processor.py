"""URL processing orchestration facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.content.cached_summary_responder import CachedSummaryResponder
from app.adapters.content.content_chunker import ContentChunker
from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.interactive_summary_service import InteractiveSummaryService
from app.adapters.content.pure_summary_service import PureSummaryService
from app.adapters.content.summarization_models import (
    InteractiveSummaryRequest,
    InteractiveSummaryResult,
)
from app.adapters.content.summarization_runtime import SummarizationRuntime
from app.adapters.content.summary_request_factory import SummaryRequestFactory
from app.adapters.content.url_flow_context_builder import URLFlowContextBuilder
from app.adapters.content.url_flow_models import (
    URLFlowContext,
    URLFlowRequest,
    URLProcessingFlowResult,
    create_chunk_llm_stub,
)
from app.adapters.content.url_post_summary_task_service import URLPostSummaryTaskService
from app.adapters.content.url_summary_delivery_service import URLSummaryDeliveryService
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.message_persistence import MessagePersistence
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.scraper.protocol import ContentScraperProtocol
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.application.ports.summaries import SummaryRepositoryPort
    from app.application.services.related_reads_service import RelatedReadsService
    from app.application.services.topic_search import TopicSearchService
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = get_logger(__name__)

__all__ = [
    "URLFlowContext",
    "URLFlowRequest",
    "URLProcessingFlowResult",
    "URLProcessor",
]


class URLProcessor:
    """Coordinate extraction, summarization, delivery, and follow-up services."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        firecrawl: ContentScraperProtocol,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
        topic_search: TopicSearchService | None = None,
        db_write_queue: DbWriteQueue | None = None,
        summary_repo: SummaryRepositoryPort | None = None,
        related_reads_service: RelatedReadsService | None = None,
        stream_coordinator_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._db_write_queue = db_write_queue
        if summary_repo is None:
            summary_repo = SqliteSummaryRepositoryAdapter(db)
        self.summary_repo = summary_repo

        self.content_extractor = ContentExtractor(
            cfg=cfg,
            db=db,
            firecrawl=firecrawl,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            quality_llm_client=openrouter,
        )
        self.content_chunker = ContentChunker(
            cfg=cfg,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )
        self.summarization_runtime = SummarizationRuntime(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            topic_search=topic_search,
            db_write_queue=db_write_queue,
        )
        self.pure_summary_service = PureSummaryService(runtime=self.summarization_runtime)
        self.summary_request_factory = SummaryRequestFactory(
            runtime=self.summarization_runtime,
            select_max_tokens=self.pure_summary_service.select_max_tokens,
            stream_coordinator_factory=stream_coordinator_factory,
        )
        self.interactive_summary_service = InteractiveSummaryService(
            runtime=self.summarization_runtime,
            request_factory=self.summary_request_factory,
            pure_summary_service=self.pure_summary_service,
        )

        self.message_persistence = MessagePersistence(db=db)

        self.cached_summary_responder = CachedSummaryResponder(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            request_repo=self.message_persistence.request_repo,
            summary_repo=self.summary_repo,
        )
        self.context_builder = URLFlowContextBuilder(
            cfg=cfg,
            content_extractor=self.content_extractor,
            content_chunker=self.content_chunker,
            response_formatter=response_formatter,
        )
        self.summary_delivery = URLSummaryDeliveryService(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            summary_repo=self.summary_repo,
            audit_func=audit_func,
            request_repo=self.message_persistence.request_repo,
        )
        self.post_summary_tasks = URLPostSummaryTaskService(
            response_formatter=response_formatter,
            summary_repo=self.summary_repo,
            article_generator=self.summarization_runtime.article_generator,
            insights_generator=self.summarization_runtime.insights_generator,
            summary_delivery=self.summary_delivery,
            related_reads_service=related_reads_service,
        )

    @property
    def audit_func(self) -> Callable[[str, str, dict], None]:
        """Public accessor for the audit callable."""
        return self._audit

    async def aclose(self, timeout: float = 5.0) -> None:
        """Drain runtime and follow-up tasks before shutdown."""
        await self.summarization_runtime.aclose(timeout=timeout)
        await self.summary_delivery.aclose(timeout=timeout)
        await self.post_summary_tasks.aclose(timeout=timeout)

    async def handle_url_flow(
        self,
        request: URLFlowRequest,
    ) -> URLProcessingFlowResult:
        """Handle complete URL processing flow from extraction to follow-up tasks."""
        cached_result = await self.cached_summary_responder.maybe_reply(
            request.message,
            request.url_text,
            correlation_id=request.correlation_id,
            interaction_id=request.interaction_id,
            silent=request.effective_silent,
        )
        if cached_result is not None:
            return cached_result

        try:
            context = await self.context_builder.build(request)

            # Resolve the model that will actually be used (routing-aware)
            display_model = self.cfg.openrouter.model
            routing_cfg = self.cfg.model_routing
            if routing_cfg.enabled:
                from app.core.content_classifier import classify_content
                from app.core.model_router import resolve_model_for_content

                tier = classify_content(context.content_text, url=request.url_text)
                display_model = resolve_model_for_content(
                    tier=tier,
                    content_length=len(context.content_text),
                    has_images=bool(context.images),
                    routing_config=routing_cfg,
                    openrouter_config=self.cfg.openrouter,
                )

            if request.on_phase_change:
                await request.on_phase_change(
                    "analyzing",
                    context.title,
                    len(context.content_text),
                    display_model,
                )

            if context.should_chunk and context.chunks:
                summary_json = await self.content_chunker.process_chunks(
                    context.chunks,
                    context.system_prompt,
                    context.chosen_lang,
                    context.req_id,
                    request.correlation_id,
                )
                if summary_json:
                    summary_json = (
                        await self.summarization_runtime.semantic_helper.enrich_with_rag_fields(
                            summary_json,
                            content_text=context.content_text,
                            chosen_lang=context.chosen_lang,
                            req_id=context.req_id,
                        )
                    )
                summary_result: InteractiveSummaryResult | None = InteractiveSummaryResult(
                    summary=summary_json,
                    llm_result=create_chunk_llm_stub(self.cfg) if summary_json else None,
                    served_from_cache=False,
                    model_used=getattr(self.cfg.openrouter, "model", None),
                )
            else:
                summary_result = await self.interactive_summary_service.summarize(
                    InteractiveSummaryRequest(
                        message=request.message,
                        content_text=context.content_text,
                        chosen_lang=context.chosen_lang,
                        system_prompt=context.system_prompt,
                        req_id=context.req_id,
                        max_chars=context.max_chars,
                        correlation_id=request.correlation_id,
                        interaction_id=request.interaction_id,
                        url_hash=context.dedupe_hash,
                        url=request.url_text,
                        silent=request.effective_silent,
                        on_phase_change=request.on_phase_change,
                        images=context.images,
                        progress_tracker=request.progress_tracker,
                    )
                )

            summary_json = summary_result.summary if summary_result else None
            if summary_json is None:
                return await self.summary_delivery.send_processing_failure(
                    message=request.message,
                    url_text=request.url_text,
                    correlation_id=request.correlation_id,
                    silent=request.silent,
                    batch_mode=request.batch_mode,
                )

            result = await self.summary_delivery.deliver_summary(
                message=request.message,
                summary_result=summary_result,
                context=context,
                correlation_id=request.correlation_id,
                interaction_id=request.interaction_id,
                silent=request.silent,
                batch_mode=request.batch_mode,
            )

            if not request.batch_mode:
                await self.post_summary_tasks.schedule_tasks(
                    request.message,
                    context.content_text,
                    context.chosen_lang,
                    context.req_id,
                    request.correlation_id,
                    summary_json,
                    needs_ru_translation=context.needs_ru_translation,
                    silent=request.silent,
                    url_hash=context.dedupe_hash,
                )

            return result
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "url_processing_failed",
                extra={"cid": request.correlation_id, "url": request.url_text, "error": str(exc)},
            )
            if not request.silent and not request.batch_mode:
                await self.response_formatter.send_error_notification(
                    request.message,
                    "processing_failed",
                    request.correlation_id or "unknown",
                )
            return URLProcessingFlowResult(success=False)
