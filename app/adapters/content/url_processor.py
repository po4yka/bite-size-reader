"""Refactored URL processor using modular components."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.content.content_chunker import ContentChunker
from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.llm_summarizer import LLMSummarizer
from app.adapters.repository_ports import (
    SummaryRepositoryPort,
    create_summary_repository,
)
from app.core.async_utils import raise_if_cancelled
from app.core.lang import LANG_RU, choose_language
from app.core.url_utils import compute_dedupe_hash, is_twitter_url, is_youtube_url
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.message_persistence import MessagePersistence
from app.migration.pipeline_shadow import PipelineShadowRunner
from app.migration.processing_orchestrator import ProcessingOrchestratorRunner
from app.prompts.manager import get_prompt_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from app.adapters.content.scraper.protocol import ContentScraperProtocol
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.core.progress_tracker import ProgressTracker
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue
    from app.services.related_reads_service import RelatedReadsService
    from app.services.topic_search import TopicSearchService

logger = logging.getLogger(__name__)


@dataclass
class URLProcessingFlowResult:
    """Result of URL processing flow for batch status tracking.

    Attributes:
        success: Whether processing completed successfully
        title: Extracted article title (from summary_250 or tldr)
        cached: Whether result was served from cache
        summary_json: Full summary payload (for batch card delivery)
        request_id: Associated request ID (for batch card delivery)
    """

    success: bool = True
    title: str | None = None
    cached: bool = False
    summary_json: dict[str, Any] | None = None
    request_id: int | None = None

    @classmethod
    def from_summary(
        cls,
        summary_json: dict[str, Any] | None,
        cached: bool = False,
        request_id: int | None = None,
    ) -> URLProcessingFlowResult:
        """Create result from summary JSON, extracting title."""
        if not summary_json:
            return cls(success=True, title=None, cached=cached)

        # Try to extract a meaningful title from summary fields
        # Priority: explicit title field > summary_250 (truncated) > tldr (truncated)
        title = None

        # Check for explicit title in metadata (some sources include it)
        if "title" in summary_json:
            title = str(summary_json["title"])[:100]

        # Fall back to summary_250 (already concise)
        if not title and summary_json.get("summary_250"):
            title = str(summary_json["summary_250"])
            # Truncate at first sentence if too long
            if len(title) > 60:
                # Find first sentence boundary
                for sep in (". ", "! ", "? "):
                    idx = title.find(sep)
                    if 0 < idx < 60:
                        title = title[: idx + 1]
                        break
                else:
                    title = title[:57] + "..."

        # Fall back to tldr
        if not title and summary_json.get("tldr"):
            title = str(summary_json["tldr"])
            if len(title) > 60:
                title = title[:57] + "..."

        return cls(
            success=True,
            title=title,
            cached=cached,
            summary_json=summary_json,
            request_id=request_id,
        )


@dataclass
class URLFlowContext:
    """Prepared context for URL extraction + summarization flow."""

    dedupe_hash: str
    req_id: int
    content_text: str
    title: str | None
    images: list[str] | None
    chosen_lang: str
    needs_ru_translation: bool
    system_prompt: str
    should_chunk: bool
    max_chars: int
    chunks: list[str] | None


def _get_system_prompt(lang: str) -> str:
    """Load the system prompt for the given language using PromptManager.

    Uses the unified PromptManager for prompt loading, caching, validation,
    and optional few-shot example injection.

    Args:
        lang: Language code ('en' or 'ru')

    Returns:
        System prompt text with optional few-shot examples
    """
    try:
        manager = get_prompt_manager()
        return manager.get_system_prompt(lang, include_examples=True, num_examples=2)
    except Exception as exc:
        logger.warning(
            "system_prompt_load_failed",
            extra={"lang": lang, "error": str(exc)},
        )
        # Minimal fallback - the PromptManager should handle most failures
        return (
            "You are a precise assistant that returns only a strict JSON object "
            "matching the provided schema. Output valid UTF-8 JSON only."
        )


async def _run_related_reads(
    service: RelatedReadsService,
    sender: Any,
    message: Any,
    summary_payload: dict[str, Any],
    request_id: int,
    correlation_id: str | None,
    lang: str,
) -> None:
    """Background task: find and send related reads for a summary."""
    try:
        items = await service.find_related(summary_payload, exclude_request_id=request_id)
        if items:
            from app.adapters.external.formatting.summary_presenter_parts.related_reads import (
                send_related_reads,
            )

            await send_related_reads(sender, message, items, lang)
    except Exception as exc:
        logger.warning(
            "related_reads_failed",
            extra={"cid": correlation_id, "error": str(exc)},
        )


def _get_processing_orchestrator(processor: Any) -> ProcessingOrchestratorRunner:
    runner = getattr(processor, "processing_orchestrator", None)
    if runner is None:
        runner = ProcessingOrchestratorRunner(processor.cfg.runtime)
        processor.processing_orchestrator = runner
    return runner


def _should_use_rust_processing_orchestrator(processor: Any, url_text: str) -> bool:
    runner = getattr(processor, "processing_orchestrator", None)
    if runner is None or not getattr(runner, "enabled", False):
        return False
    try:
        return not (is_twitter_url(url_text) or is_youtube_url(url_text))
    except Exception:
        return True


async def _handle_url_flow_via_rust_orchestrator(
    processor: Any,
    *,
    message: Any,
    url_text: str,
    correlation_id: str | None,
    interaction_id: int | None,
    silent: bool,
    batch_mode: bool,
    notify_silent: bool,
    on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]] | None,
) -> URLProcessingFlowResult:
    base_temperature_value = getattr(processor.cfg.openrouter, "temperature", 0.2)
    base_temperature = (
        base_temperature_value if isinstance(base_temperature_value, (int, float)) else 0.2
    )
    base_top_p_value = getattr(processor.cfg.openrouter, "top_p", None)
    base_top_p = base_top_p_value if isinstance(base_top_p_value, (int, float)) else 0.9
    fallback_models_value = getattr(processor.cfg.openrouter, "fallback_models", ())
    fallback_models = (
        [model for model in fallback_models_value if isinstance(model, str)]
        if isinstance(fallback_models_value, (list, tuple))
        else []
    )
    flash_fallback_models_value = getattr(processor.cfg.openrouter, "flash_fallback_models", ())
    flash_fallback_models = (
        [model for model in flash_fallback_models_value if isinstance(model, str)]
        if isinstance(flash_fallback_models_value, (list, tuple))
        else []
    )

    if not notify_silent:
        await processor.response_formatter.send_url_accepted_notification(
            message, url_text, correlation_id, silent=notify_silent
        )

    async def _handle_event(event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "").strip().lower()
        if event_type == "phase" and on_phase_change is not None:
            phase = str(event.get("phase") or "").strip().lower()
            title = event.get("title")
            model = event.get("model")
            content_length = event.get("content_length")
            await on_phase_change(
                phase,
                str(title) if isinstance(title, str) else None,
                int(content_length) if isinstance(content_length, int) else None,
                str(model) if isinstance(model, str) else None,
            )
        elif (
            event_type == "draft_delta"
            and not notify_silent
            and hasattr(processor.response_formatter, "send_message_draft")
        ):
            delta = str(event.get("delta") or "").strip()
            if delta:
                await processor.response_formatter.send_message_draft(message, delta)

    result = await _get_processing_orchestrator(processor).execute_url_flow(
        correlation_id=correlation_id,
        input_url=url_text,
        chat_id=getattr(getattr(message, "chat", None), "id", None),
        user_id=getattr(getattr(message, "from_user", None), "id", None),
        input_message_id=getattr(message, "id", getattr(message, "message_id", None)),
        silent=silent,
        preferred_language=processor.cfg.runtime.preferred_lang,
        route_version=1,
        prompt_version=processor.cfg.runtime.summary_prompt_version,
        enable_chunking=bool(getattr(processor.cfg.runtime, "enable_chunking", False)),
        configured_chunk_max_chars=int(getattr(processor.cfg.runtime, "chunk_max_chars", 200000)),
        primary_model=processor.cfg.openrouter.model,
        long_context_model=processor.cfg.openrouter.long_context_model,
        fallback_models=fallback_models,
        flash_model=processor.cfg.openrouter.flash_model,
        flash_fallback_models=flash_fallback_models,
        structured_output_mode=processor.cfg.openrouter.structured_output_mode,
        temperature=base_temperature,
        top_p=base_top_p,
        json_temperature=processor.cfg.openrouter.summary_temperature_json_fallback
        or max(0.0, min(0.5, base_temperature - 0.05)),
        json_top_p=processor.cfg.openrouter.summary_top_p_json_fallback
        or max(0.0, min(0.95, base_top_p)),
        vision_model=getattr(getattr(processor.cfg, "attachment", None), "vision_model", None),
        enable_two_pass_enrichment=bool(
            getattr(processor.cfg.runtime, "summary_two_pass_enabled", False)
        ),
        web_search_context=None,
        on_event=_handle_event,
    )

    status = str(result.get("status") or "error").strip().lower()
    request_id = result.get("request_id") if isinstance(result.get("request_id"), int) else None
    summary_json = result.get("summary") if isinstance(result.get("summary"), dict) else None
    content_text = (
        result.get("content_text") if isinstance(result.get("content_text"), str) else None
    )
    chosen_lang = (
        str(result.get("chosen_lang") or processor.cfg.runtime.preferred_lang).strip().lower()
        or "en"
    )
    needs_ru_translation = bool(result.get("needs_ru_translation"))
    dedupe_hash = result.get("dedupe_hash") if isinstance(result.get("dedupe_hash"), str) else None

    if status == "error" or summary_json is None:
        if not silent and not batch_mode:
            await processor.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
                details=str(result.get("error_text") or ""),
            )
        return URLProcessingFlowResult(success=False, request_id=request_id)

    if not silent and not batch_mode:
        if status == "cached":
            await processor.response_formatter.send_cached_summary_notification(
                message, silent=notify_silent
            )
        llm_stub = _create_chunk_llm_stub(processor.cfg)
        model = result.get("model")
        if isinstance(model, str) and model:
            llm_stub.model = model
        await processor.response_formatter.send_structured_summary_response(
            message,
            summary_json,
            llm_stub,
            chunks=result.get("chunk_count")
            if isinstance(result.get("chunk_count"), int)
            else None,
            summary_id=f"req:{request_id}" if request_id else None,
            correlation_id=correlation_id,
        )

    if interaction_id:
        await async_safe_update_user_interaction(
            processor.db,
            interaction_id=interaction_id,
            response_sent=True,
            response_type="summary",
            request_id=request_id,
        )

    if content_text and request_id and not batch_mode:
        await processor._schedule_post_summary_tasks(
            message,
            content_text,
            chosen_lang,
            request_id,
            correlation_id,
            summary_json,
            needs_ru_translation=needs_ru_translation,
            silent=silent,
            url_hash=dedupe_hash,
        )

    return URLProcessingFlowResult.from_summary(
        summary_json,
        cached=status == "cached",
        request_id=request_id,
    )


def _get_summary_response_type(summarizer: Any, *, mode: str | None = None) -> str:
    workflow = getattr(summarizer, "_workflow", None)
    builder = getattr(workflow, "build_structured_response_format", None)
    default = "json_object" if mode == "json_object" else "unknown"
    if not callable(builder):
        return default
    response_format = builder(mode=mode) if mode is not None else builder()
    if asyncio.iscoroutine(response_format):
        response_format.close()
        return default
    if isinstance(response_format, dict):
        response_type = str(response_format.get("type") or default).strip()
        return response_type or default
    return default


def _schedule_tracked_task(
    task_registry: set[asyncio.Task[Any]],
    coro: Coroutine[Any, Any, Any],
    correlation_id: str | None,
    label: str,
    *,
    schedule_error_event: str,
    task_error_event: str,
) -> asyncio.Task[Any] | None:
    try:
        task: asyncio.Task[Any] = asyncio.create_task(coro)
        task_registry.add(task)
        task.add_done_callback(task_registry.discard)
    except RuntimeError as exc:
        logger.error(
            schedule_error_event,
            extra={"cid": correlation_id, "label": label, "error": str(exc)},
        )
        return None

    def _log_task_error(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(
                task_error_event,
                extra={"cid": correlation_id, "label": label, "error": str(exc)},
            )

    task.add_done_callback(_log_task_error)
    return task


async def _await_persistence_task(task: asyncio.Task[Any] | None) -> None:
    if task is None:
        return
    try:
        await task
    except Exception as exc:
        raise_if_cancelled(exc)
        logger.error("persistence_task_failed", extra={"error": str(exc)})


def _create_chunk_llm_stub(cfg: Any) -> Any:
    return type(
        "LLMStub",
        (),
        {
            "status": "ok",
            "latency_ms": None,
            "model": cfg.openrouter.model,
            "cost_usd": None,
            "tokens_prompt": None,
            "tokens_completion": None,
            "structured_output_used": True,
            "structured_output_mode": cfg.openrouter.structured_output_mode,
        },
    )()


def _schedule_chunk_persistence_if_needed(
    processor: Any,
    *,
    context: URLFlowContext,
    summary_json: dict[str, Any],
    correlation_id: str | None,
    interaction_id: int | None,
    silent: bool,
) -> asyncio.Task[Any] | None:
    if not (context.should_chunk and context.chunks):
        return None
    return _schedule_tracked_task(
        processor._background_tasks,
        processor._persist_summary(
            req_id=context.req_id,
            chosen_lang=context.chosen_lang,
            summary_json=summary_json,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=silent,
        ),
        correlation_id,
        "persist_summary",
        schedule_error_event="persistence_task_schedule_failed",
        task_error_event="persistence_task_failed",
    )


class URLProcessor:
    """Refactored URL processor using modular components."""

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
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._db_write_queue = db_write_queue
        self.summary_repo = summary_repo or create_summary_repository(db)
        self._related_reads_service = related_reads_service

        # Initialize modular components
        self.content_extractor = ContentExtractor(
            cfg=cfg,
            db=db,
            firecrawl=firecrawl,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.content_chunker = ContentChunker(
            cfg=cfg,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.llm_summarizer = LLMSummarizer(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            topic_search=topic_search,
            db_write_queue=db_write_queue,
        )

        self.message_persistence = MessagePersistence(db=db)
        self.pipeline_shadow = PipelineShadowRunner(cfg.runtime)
        self.processing_orchestrator = ProcessingOrchestratorRunner(cfg.runtime)
        self.content_chunker.pipeline_shadow = self.pipeline_shadow
        # Registry for tracking background tasks to prevent GC and ensure shutdown
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def aclose(self, timeout: float = 5.0) -> None:
        """Wait for all background tasks to complete before closing."""
        # 1. Drain workflow tasks via summarizer
        if hasattr(self, "llm_summarizer") and hasattr(self.llm_summarizer, "workflow"):
            await self.llm_summarizer.workflow.aclose(timeout=timeout)

        # 2. Drain local background tasks
        if not self._background_tasks:
            return

        logger.info(
            "url_processor_shutdown_draining", extra={"task_count": len(self._background_tasks)}
        )
        # Create a list because discard() modifies the set
        tasks = list(self._background_tasks)
        if tasks:
            try:
                async with asyncio.timeout(timeout):
                    await asyncio.gather(*tasks, return_exceptions=True)
            except TimeoutError:
                logger.warning(
                    "url_processor_shutdown_timeout", extra={"pending": len(self._background_tasks)}
                )
        logger.info("url_processor_shutdown_complete")

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
        batch_mode: bool = False,
        on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]]
        | None = None,
        progress_tracker: ProgressTracker | None = None,
    ) -> URLProcessingFlowResult:
        """Handle complete URL processing flow from extraction to summarization.

        Args:
            silent: If True, suppress all Telegram responses and only persist to database
            batch_mode: If True, suppress intermediate notifications and post-summary
                tasks to reduce message flooding during multi-URL batch processing.
                The final summary response and error notifications are also suppressed;
                callers are expected to send a compact batch completion card instead.
            on_phase_change: Optional async callback invoked when processing enters
                a new phase (e.g. ``"extracting"``, ``"analyzing"``).

        Returns:
            URLProcessingFlowResult with success status and extracted title
        """
        # In batch mode, suppress individual per-URL notifications from sub-components.
        # The batch progress message handles status display via on_phase_change callback.
        notify_silent = silent or batch_mode

        if _should_use_rust_processing_orchestrator(self, url_text):
            return await _handle_url_flow_via_rust_orchestrator(
                self,
                message=message,
                url_text=url_text,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                silent=silent,
                batch_mode=batch_mode,
                notify_silent=notify_silent,
                on_phase_change=on_phase_change,
            )

        cached_result = await self._maybe_reply_with_cached_summary(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=notify_silent,
        )
        if cached_result is not None:
            return cached_result

        try:
            context = await self._prepare_url_flow_context(
                message=message,
                url_text=url_text,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                notify_silent=notify_silent,
                silent=silent,
                batch_mode=batch_mode,
                on_phase_change=on_phase_change,
                progress_tracker=progress_tracker,
            )
            if on_phase_change:
                await on_phase_change(
                    "analyzing",
                    context.title,
                    len(context.content_text),
                    self.cfg.openrouter.model,
                )

            summary_json = await self._summarize_url_content(
                message=message,
                url_text=url_text,
                context=context,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                notify_silent=notify_silent,
                on_phase_change=on_phase_change,
                progress_tracker=progress_tracker,
            )

            if summary_json is None:
                return await self._handle_summarization_failure(
                    message=message,
                    url_text=url_text,
                    correlation_id=correlation_id,
                    silent=silent,
                    batch_mode=batch_mode,
                )

            persist_task = _schedule_chunk_persistence_if_needed(
                self,
                context=context,
                summary_json=summary_json,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                silent=silent,
            )

            # Format and send the response (skip if silent or batch)
            if not silent and not batch_mode:
                llm_result = self.llm_summarizer.last_llm_result or _create_chunk_llm_stub(self.cfg)
                # Pass request ID prefixed with 'req:' for action button callbacks
                await self.response_formatter.send_structured_summary_response(
                    message,
                    summary_json,
                    llm_result,
                    chunks=len(context.chunks) if context.should_chunk and context.chunks else None,
                    summary_id=f"req:{context.req_id}" if context.req_id else None,
                    correlation_id=correlation_id,
                )

            # Skip post-summary background tasks in batch mode to reduce noise
            if not batch_mode:
                await self._schedule_post_summary_tasks(
                    message,
                    context.content_text,
                    context.chosen_lang,
                    context.req_id,
                    correlation_id,
                    summary_json,
                    needs_ru_translation=context.needs_ru_translation,
                    silent=silent,
                    url_hash=context.dedupe_hash,
                )

            # For silent or batch mode, we need to ensure persistence completes
            if (silent or batch_mode) and persist_task:
                await _await_persistence_task(persist_task)

            # Return result with extracted title and payload for batch card delivery
            return URLProcessingFlowResult.from_summary(summary_json, request_id=context.req_id)

        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "url_processing_failed",
                extra={"cid": correlation_id, "url": url_text, "error": str(exc)},
            )
            if not silent and not batch_mode:
                await self.response_formatter.send_error_notification(
                    message,
                    "processing_failed",
                    correlation_id or "unknown",
                )
            return URLProcessingFlowResult(success=False)

    async def _prepare_url_flow_context(
        self,
        *,
        message: Any,
        url_text: str,
        correlation_id: str | None,
        interaction_id: int | None,
        notify_silent: bool,
        silent: bool,
        batch_mode: bool,
        on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]]
        | None,
        progress_tracker: ProgressTracker | None,
    ) -> URLFlowContext:
        """Extract content and build the processing context for summarization."""
        dedupe_hash = compute_dedupe_hash(url_text)
        if on_phase_change:
            await on_phase_change("extracting", None, None, None)

        (
            req_id,
            content_text,
            _content_source,
            detected,
            title,
            images,
        ) = await self.content_extractor.extract_and_process_content(
            message,
            url_text,
            correlation_id,
            interaction_id,
            notify_silent,
            progress_tracker,
        )
        pipeline_shadow = getattr(self, "pipeline_shadow", None)
        if pipeline_shadow is not None and pipeline_shadow.options.enabled:
            extraction_snapshot = await pipeline_shadow.resolve_extraction_adapter(
                correlation_id=correlation_id,
                request_id=req_id,
                url_hash=dedupe_hash,
                content_text=content_text,
                content_source=_content_source,
                title=title,
                images_count=len(images or []),
            )
            logger.debug(
                "m3_pipeline_extraction_adapter_resolved",
                extra={
                    "cid": correlation_id,
                    "request_id": req_id,
                    "language_hint": extraction_snapshot.get("language_hint"),
                    "low_value": extraction_snapshot.get("low_value"),
                },
            )

        enable_chunking_value = getattr(self.cfg.runtime, "enable_chunking", False)
        enable_chunking = (
            enable_chunking_value if isinstance(enable_chunking_value, bool) else False
        )
        configured_chunk_max_chars_value = getattr(self.cfg.runtime, "chunk_max_chars", 200000)
        configured_chunk_max_chars = (
            configured_chunk_max_chars_value
            if isinstance(configured_chunk_max_chars_value, int)
            else 200000
        )
        base_temperature_value = getattr(self.cfg.openrouter, "temperature", 0.2)
        base_temperature = (
            base_temperature_value if isinstance(base_temperature_value, (int, float)) else 0.2
        )
        base_top_p_value = getattr(self.cfg.openrouter, "top_p", None)
        base_top_p = base_top_p_value if isinstance(base_top_p_value, (int, float)) else 0.9
        fallback_models_value = getattr(self.cfg.openrouter, "fallback_models", ())
        fallback_models = (
            [model for model in fallback_models_value if isinstance(model, str)]
            if isinstance(fallback_models_value, (list, tuple))
            else []
        )
        flash_fallback_models_value = getattr(self.cfg.openrouter, "flash_fallback_models", ())
        flash_fallback_models = (
            [model for model in flash_fallback_models_value if isinstance(model, str)]
            if isinstance(flash_fallback_models_value, (list, tuple))
            else []
        )
        json_temperature = self.cfg.openrouter.summary_temperature_json_fallback or max(
            0.0, min(0.5, base_temperature - 0.05)
        )
        json_top_p = self.cfg.openrouter.summary_top_p_json_fallback or max(
            0.0, min(0.95, base_top_p)
        )
        processing_plan = await _get_processing_orchestrator(self).resolve_url_processing_plan(
            correlation_id=correlation_id,
            request_id=req_id,
            dedupe_hash=dedupe_hash,
            content_text=content_text,
            detected_language=detected,
            preferred_language=self.cfg.runtime.preferred_lang,
            silent=silent,
            enable_chunking=enable_chunking,
            configured_chunk_max_chars=configured_chunk_max_chars,
            primary_model=self.cfg.openrouter.model,
            long_context_model=self.cfg.openrouter.long_context_model,
            schema_response_type=_get_summary_response_type(self.llm_summarizer),
            json_object_response_type=_get_summary_response_type(
                self.llm_summarizer, mode="json_object"
            ),
            max_tokens_schema=None,
            max_tokens_json_object=None,
            base_temperature=base_temperature,
            base_top_p=base_top_p,
            json_temperature=json_temperature,
            json_top_p=json_top_p,
            fallback_models=fallback_models,
            flash_model=self.cfg.openrouter.flash_model,
            flash_fallback_models=flash_fallback_models,
        )
        chosen_lang = str(
            processing_plan.get("chosen_lang")
            or choose_language(self.cfg.runtime.preferred_lang, detected)
        )
        needs_ru_translation = bool(
            processing_plan.get(
                "needs_ru_translation",
                not silent and LANG_RU not in (detected, chosen_lang),
            )
        )
        system_prompt = _get_system_prompt(chosen_lang)

        logger.debug(
            "language_choice",
            extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
        )
        if not silent and not batch_mode:
            content_preview = (
                content_text[:150] + "..." if len(content_text) > 150 else content_text
            )
            await self.response_formatter.send_language_detection_notification(
                message,
                detected,
                content_preview,
                url=url_text,
                silent=silent,
            )

        chunk_plan = processing_plan.get("chunk_plan")
        raw_chunks = chunk_plan.get("chunks") if isinstance(chunk_plan, dict) else None
        chunks = (
            [item.strip() for item in raw_chunks if isinstance(item, str) and item.strip()]
            if isinstance(raw_chunks, list)
            else None
        )
        should_chunk = bool(processing_plan.get("summary_strategy") == "chunked" and chunks)
        max_chars = int(
            processing_plan.get("effective_max_chars") or self.cfg.runtime.chunk_max_chars
        )

        logger.debug(
            "processing_orchestrator_url_plan_resolved",
            extra={
                "cid": correlation_id,
                "request_id": req_id,
                "strategy": processing_plan.get("summary_strategy"),
                "summary_model": processing_plan.get("summary_model"),
                "request_plan_count": (
                    processing_plan.get("single_pass_request_plan", {}).get("request_count")
                    if isinstance(processing_plan.get("single_pass_request_plan"), dict)
                    else None
                ),
                "chunk_count": len(chunks) if chunks else 0,
            },
        )

        if not batch_mode:
            await self.response_formatter.send_content_analysis_notification(
                message,
                len(content_text),
                max_chars,
                should_chunk,
                chunks,
                self.cfg.openrouter.structured_output_mode,
                silent=silent,
            )

        return URLFlowContext(
            dedupe_hash=dedupe_hash,
            req_id=req_id,
            content_text=content_text,
            title=title,
            images=images,
            chosen_lang=chosen_lang,
            needs_ru_translation=needs_ru_translation,
            system_prompt=system_prompt,
            should_chunk=should_chunk,
            max_chars=max_chars,
            chunks=chunks,
        )

    async def _compute_chunk_strategy(
        self,
        *,
        content_text: str,
        chosen_lang: str,
        correlation_id: str | None,
        request_id: int | None,
    ) -> tuple[bool, int, list[str] | None]:
        """Choose chunking strategy, with optional Rust-authoritative M3 preprocessing."""
        should_chunk, max_chars, chunks = self.content_chunker.should_chunk_content(
            content_text, chosen_lang
        )
        long_context_model = self.cfg.openrouter.long_context_model
        if should_chunk and long_context_model:
            logger.info(
                "chunking_bypassed_long_context",
                extra={
                    "cid": correlation_id,
                    "long_context_model": long_context_model,
                    "content_length": len(content_text),
                },
            )
            should_chunk = False
            chunks = None

        pipeline_shadow = getattr(self, "pipeline_shadow", None)
        if pipeline_shadow is not None and pipeline_shadow.options.enabled:
            enable_chunking_value = getattr(self.cfg.runtime, "enable_chunking", False)
            enable_chunking = (
                enable_chunking_value if isinstance(enable_chunking_value, bool) else False
            )
            lc_model = long_context_model if isinstance(long_context_model, str) else None
            rust_snapshot = await pipeline_shadow.resolve_chunking_preprocess(
                correlation_id=correlation_id,
                request_id=request_id,
                content_text=content_text,
                enable_chunking=enable_chunking,
                max_chars=max_chars,
                long_context_model=lc_model,
            )
            rust_should_chunk = bool(rust_snapshot.get("should_chunk", False))
            max_chars = int(rust_snapshot.get("max_chars", max_chars))
            should_chunk = rust_should_chunk
            if not should_chunk:
                should_chunk = False
                chunks = None
            else:
                chunk_plan = await pipeline_shadow.resolve_chunk_sentence_plan(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    content_text=content_text,
                    lang=chosen_lang,
                    max_chars=max_chars,
                )
                rust_chunks_raw = chunk_plan.get("chunks")
                if isinstance(rust_chunks_raw, list):
                    rust_chunks = [
                        item.strip()
                        for item in rust_chunks_raw
                        if isinstance(item, str) and item.strip()
                    ]
                    chunks = rust_chunks or None
                    should_chunk = chunks is not None
                else:
                    chunks = None
                    should_chunk = False

        logger.info(
            "content_handling",
            extra={
                "cid": correlation_id,
                "length": len(content_text),
                "should_chunk": should_chunk,
                "chunks": len(chunks) if chunks else 0,
            },
        )
        return should_chunk, max_chars, chunks

    async def _summarize_url_content(
        self,
        *,
        message: Any,
        url_text: str,
        context: URLFlowContext,
        correlation_id: str | None,
        interaction_id: int | None,
        notify_silent: bool,
        on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]]
        | None,
        progress_tracker: ProgressTracker | None,
    ) -> dict[str, Any] | None:
        """Run either chunked or single-pass summarization."""
        if context.should_chunk and context.chunks:
            summary_json = await self.content_chunker.process_chunks(
                context.chunks,
                context.system_prompt,
                context.chosen_lang,
                context.req_id,
                correlation_id,
            )
            if summary_json:
                return await self.llm_summarizer.enrich_summary_rag_fields(
                    summary_json,
                    content_text=context.content_text,
                    chosen_lang=context.chosen_lang,
                    req_id=context.req_id,
                )
            return summary_json

        return await self.llm_summarizer.summarize_content(
            message,
            context.content_text,
            context.chosen_lang,
            context.system_prompt,
            context.req_id,
            context.max_chars,
            correlation_id,
            interaction_id,
            url_hash=context.dedupe_hash,
            url=url_text,
            silent=notify_silent,
            on_phase_change=on_phase_change,
            images=context.images,
            progress_tracker=progress_tracker,
        )

    async def _handle_summarization_failure(
        self,
        *,
        message: Any,
        url_text: str,
        correlation_id: str | None,
        silent: bool,
        batch_mode: bool,
    ) -> URLProcessingFlowResult:
        """Notify and return flow failure payload when summarization fails."""
        logger.error("summarization_failed", extra={"cid": correlation_id, "url": url_text})
        if not silent and not batch_mode:
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
            )
        return URLProcessingFlowResult(success=False)

    async def _maybe_reply_with_cached_summary(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> URLProcessingFlowResult | None:
        """Check for cached summary and reply if found.

        Returns URLProcessingFlowResult if a cached response was sent, None otherwise.
        """
        try:
            dedupe_hash = compute_dedupe_hash(url_text)

            request_row = (
                await self.message_persistence.request_repo.async_get_request_by_dedupe_hash(
                    dedupe_hash
                )
            )
            request_id = request_row.get("id") if isinstance(request_row, dict) else None
            if not isinstance(request_id, int):
                return None

            cached = await self.summary_repo.async_get_summary_by_request(request_id)
            payload = cached.get("json_payload") if isinstance(cached, dict) else None
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = None

            if isinstance(payload, dict):
                logger.info(
                    "cache_hit",
                    extra={"cid": correlation_id, "url": url_text, "hash": dedupe_hash[:12]},
                )
                # Update correlation_id on the existing request for cache hit
                if correlation_id:
                    try:
                        await self.message_persistence.request_repo.async_update_request_correlation_id(
                            request_id, correlation_id
                        )
                    except Exception as exc:
                        logger.warning(
                            "cache_hit_cid_update_failed",
                            extra={"error": str(exc), "cid": correlation_id},
                        )
                if not silent:
                    await self.response_formatter.send_cached_summary_notification(
                        message, silent=silent
                    )
                    await self.response_formatter.send_structured_summary_response(
                        message,
                        payload,
                        _create_chunk_llm_stub(self.cfg),
                        summary_id=f"req:{request_id}" if request_id else None,
                    )

                # Update interaction if provided
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.db,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="summary",
                        request_id=request_id if isinstance(request_id, int) else None,
                    )
                return URLProcessingFlowResult.from_summary(
                    payload, cached=True, request_id=request_id
                )
        except Exception as exc:
            logger.warning(
                "cache_check_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
        return None

    async def _persist_summary(
        self,
        req_id: int,
        chosen_lang: str,
        summary_json: dict[str, Any],
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool,
    ) -> None:
        """Persist summary to database."""
        try:
            new_version = await self.summary_repo.async_upsert_summary(
                request_id=req_id,
                lang=chosen_lang,
                json_payload=summary_json,
                is_read=not silent,
            )
            await self.message_persistence.request_repo.async_update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="summary",
                    request_id=req_id,
                )
        except Exception as exc:
            logger.error(
                "summary_persistence_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def _schedule_post_summary_tasks(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        summary: dict[str, Any],
        *,
        needs_ru_translation: bool,
        silent: bool,
        url_hash: str | None,
    ) -> None:
        if needs_ru_translation:
            _schedule_tracked_task(
                self._background_tasks,
                self._maybe_send_russian_translation(
                    message,
                    summary,
                    req_id,
                    correlation_id,
                    needs_ru_translation,
                    url_hash=url_hash,
                    source_lang=chosen_lang,
                ),
                correlation_id,
                "ru_translation",
                schedule_error_event="background_task_schedule_failed",
                task_error_event="background_task_failed",
            )

        reader_mode = False
        if not silent:
            try:
                reader_mode = await self.response_formatter.is_reader_mode(message)
            except Exception:
                reader_mode = False

        if not silent:
            if not reader_mode:
                try:
                    await self.response_formatter.safe_reply(
                        message,
                        "🧠 Generating additional research insights…",
                    )
                except Exception as exc:
                    raise_if_cancelled(exc)

        _schedule_tracked_task(
            self._background_tasks,
            self._handle_additional_insights(
                message,
                content_text,
                chosen_lang,
                req_id,
                correlation_id,
                summary=summary,
                silent=silent,
                url_hash=url_hash,
            ),
            correlation_id,
            "additional_insights",
            schedule_error_event="background_task_schedule_failed",
            task_error_event="background_task_failed",
        )

        if not silent:
            topics = summary.get("key_ideas") or []
            tags = summary.get("topic_tags") or []
            if (topics or tags) and isinstance(topics, list) and isinstance(tags, list):
                if not reader_mode:
                    try:
                        await self.response_formatter.safe_reply(
                            message,
                            "📝 Crafting a standalone article from topics & tags…",
                        )
                    except Exception as exc:
                        raise_if_cancelled(exc)

                if not reader_mode:
                    _schedule_tracked_task(
                        self._background_tasks,
                        self._handle_custom_article(
                            message,
                            chosen_lang,
                            req_id,
                            correlation_id,
                            topics,
                            tags,
                            url_hash=url_hash,
                        ),
                        correlation_id,
                        "custom_article",
                        schedule_error_event="background_task_schedule_failed",
                        task_error_event="background_task_failed",
                    )

        if self._related_reads_service is not None and not silent:
            _schedule_tracked_task(
                self._background_tasks,
                _run_related_reads(
                    self._related_reads_service,
                    self.response_formatter.sender,
                    message,
                    summary,
                    req_id,
                    correlation_id,
                    chosen_lang,
                ),
                correlation_id,
                "related_reads",
                schedule_error_event="background_task_schedule_failed",
                task_error_event="background_task_failed",
            )

    async def _maybe_send_russian_translation(
        self,
        message: Any,
        summary: dict[str, Any],
        req_id: int,
        correlation_id: str | None,
        needs_translation: bool,
        *,
        url_hash: str | None = None,
        source_lang: str | None = None,
    ) -> None:
        """Generate and send an adapted Russian translation of the summary when required."""
        if not needs_translation:
            return

        try:
            translated = await self.llm_summarizer.translate_summary_to_ru(
                summary,
                req_id=req_id,
                correlation_id=correlation_id,
                url_hash=url_hash,
                source_lang=source_lang,
            )
            if translated:
                await self.response_formatter.send_russian_translation(
                    message, translated, correlation_id=correlation_id
                )
                return

            await self.response_formatter.safe_reply(
                message,
                (
                    "⚠️ Unable to generate Russian translation right now. Error ID: "
                    f"{correlation_id or 'unknown'}."
                ),
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "ru_translation_failed", extra={"cid": correlation_id, "error": str(exc)}
            )
            try:
                await self.response_formatter.safe_reply(
                    message,
                    f"⚠️ Russian translation failed. Error ID: {correlation_id or 'unknown'}.",
                )
            except Exception as exc:
                raise_if_cancelled(exc)

    async def _handle_additional_insights(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        *,
        summary: dict[str, Any] | None = None,
        silent: bool = False,
        url_hash: str | None = None,
    ) -> None:
        """Generate and persist additional insights using the LLM."""
        logger.info(
            "insights_flow_started",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            insights = await self.llm_summarizer.generate_additional_insights(
                message,
                content_text=content_text,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                summary=summary,
                url_hash=url_hash,
            )

            if insights:
                logger.info(
                    "insights_generated_successfully",
                    extra={
                        "cid": correlation_id,
                        "facts_count": len(insights.get("new_facts", [])),
                        "has_overview": bool(insights.get("topic_overview")),
                    },
                )

                should_notify = not silent
                if should_notify:
                    try:
                        should_notify = not (await self.response_formatter.is_reader_mode(message))
                    except Exception:
                        should_notify = True

                if should_notify:
                    await self.response_formatter.send_additional_insights_message(
                        message, insights, correlation_id
                    )
                    logger.info("insights_message_sent", extra={"cid": correlation_id})
                else:
                    logger.info(
                        "insights_notification_skipped",
                        extra={"cid": correlation_id, "reason": "reader_mode_or_silent"},
                    )

                try:
                    await self.summary_repo.async_update_summary_insights(req_id, insights)
                    logger.debug(
                        "insights_persisted", extra={"cid": correlation_id, "request_id": req_id}
                    )
                except Exception as exc:
                    raise_if_cancelled(exc)
                    logger.error(
                        "persist_insights_error",
                        extra={"cid": correlation_id, "error": str(exc)},
                    )
            else:
                logger.warning(
                    "insights_generation_returned_empty",
                    extra={"cid": correlation_id, "reason": "LLM returned None or empty insights"},
                )

        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "insights_flow_error",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def _handle_custom_article(
        self,
        message: Any,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        topics: list[Any],
        tags: list[Any],
        *,
        url_hash: str | None = None,
    ) -> None:
        """Generate a standalone custom article based on extracted topics/tags."""
        try:
            article = await self.llm_summarizer.generate_custom_article(
                message,
                chosen_lang=chosen_lang,
                req_id=req_id,
                topics=[str(x) for x in topics if str(x).strip()],
                tags=[str(x) for x in tags if str(x).strip()],
                correlation_id=correlation_id,
                url_hash=url_hash,
            )
            if article:
                await self.response_formatter.send_custom_article(message, article)
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.error(
                "custom_article_flow_error",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def translate_summary_to_ru(
        self,
        summary: dict[str, Any],
        *,
        req_id: int,
        correlation_id: str | None = None,
        url_hash: str | None = None,
        source_lang: str | None = None,
    ) -> str | None:
        """Translate a shaped summary to fluent Russian."""
        return await self.llm_summarizer.translate_summary_to_ru(
            summary,
            req_id=req_id,
            correlation_id=correlation_id,
            url_hash=url_hash,
            source_lang=source_lang,
        )

    async def clear_cache(self) -> int:
        """Clear the extraction cache."""
        if hasattr(self.content_extractor, "_cache"):
            return await self.content_extractor._cache.clear()
        return 0
