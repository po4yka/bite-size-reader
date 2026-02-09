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
from app.core.async_utils import raise_if_cancelled
from app.core.lang import LANG_RU, choose_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.message_persistence import MessagePersistence
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.prompts.manager import get_prompt_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from app.adapters.external.firecrawl_parser import FirecrawlClient
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.core.progress_tracker import ProgressTracker
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue
    from app.services.topic_search import TopicSearchService

logger = logging.getLogger(__name__)


@dataclass
class URLProcessingFlowResult:
    """Result of URL processing flow for batch status tracking.

    Attributes:
        success: Whether processing completed successfully
        title: Extracted article title (from summary_250 or tldr)
        cached: Whether result was served from cache
    """

    success: bool = True
    title: str | None = None
    cached: bool = False

    @classmethod
    def from_summary(
        cls, summary_json: dict[str, Any] | None, cached: bool = False
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

        return cls(success=True, title=title, cached=cached)


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


class URLProcessor:
    """Refactored URL processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        firecrawl: FirecrawlClient,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
        topic_search: TopicSearchService | None = None,
        db_write_queue: DbWriteQueue | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._db_write_queue = db_write_queue
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)

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
        # Registry for tracking background tasks to prevent GC and ensure shutdown
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def _schedule_persistence_task(
        self, coro: Coroutine[Any, Any, Any], correlation_id: str | None, label: str
    ) -> asyncio.Task[Any] | None:
        """Run a persistence task without blocking the main flow."""
        try:
            task: asyncio.Task[Any] = asyncio.create_task(coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError as exc:
            logger.error(
                "persistence_task_schedule_failed",
                extra={"cid": correlation_id, "label": label, "error": str(exc)},
            )
            return None

        def _log_task_error(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "persistence_task_failed",
                    extra={"cid": correlation_id, "label": label, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

    def _schedule_background_task(
        self, coro: Coroutine[Any, Any, Any], correlation_id: str | None, label: str
    ) -> asyncio.Task[Any] | None:
        """Run a background task without blocking the main flow."""
        try:
            task: asyncio.Task[Any] = asyncio.create_task(coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError as exc:
            logger.error(
                "background_task_schedule_failed",
                extra={"cid": correlation_id, "label": label, "error": str(exc)},
            )
            return None

        def _log_task_error(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "background_task_failed",
                    extra={"cid": correlation_id, "label": label, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

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
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
                )
            except TimeoutError:
                logger.warning(
                    "url_processor_shutdown_timeout", extra={"pending": len(self._background_tasks)}
                )
            except Exception as e:
                logger.error("url_processor_shutdown_error", extra={"error": str(e)})
        logger.info("url_processor_shutdown_complete")

    async def _await_persistence_task(self, task: asyncio.Task | None) -> None:
        """Await a scheduled persistence task when required (silent flows)."""
        if task is None:
            return
        try:
            await task
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.error("persistence_task_failed", extra={"error": str(exc)})

    def _create_chunk_llm_stub(self) -> Any:
        """Create a stub LLM result for chunked processing."""
        return type(
            "LLMStub",
            (),
            {
                "status": "ok",
                "latency_ms": None,
                "model": self.cfg.openrouter.model,
                "cost_usd": None,
                "tokens_prompt": None,
                "tokens_completion": None,
                "structured_output_used": True,
                "structured_output_mode": self.cfg.openrouter.structured_output_mode,
            },
        )()

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
            norm = normalize_url(url_text)
            dedupe_hash = url_hash_sha256(norm)
            # Signal phase: extracting content
            if on_phase_change:
                await on_phase_change("extracting", None, None, None)

            # Extract and process content
            (
                req_id,
                content_text,
                _content_source,
                detected,
                title,
                images,
            ) = await self.content_extractor.extract_and_process_content(
                message, url_text, correlation_id, interaction_id, notify_silent, progress_tracker
            )

            # Choose language and load system prompt
            chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
            needs_ru_translation = not silent and LANG_RU not in (detected, chosen_lang)
            system_prompt = await self._load_system_prompt(chosen_lang)

            logger.debug(
                "language_choice",
                extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
            )

            # Notify: language detected with content preview (skip if silent or batch)
            if not silent and not batch_mode:
                content_preview = (
                    content_text[:150] + "..." if len(content_text) > 150 else content_text
                )
                await self.response_formatter.send_language_detection_notification(
                    message, detected, content_preview, url=url_text, silent=silent
                )

            # Check if content should be chunked
            should_chunk, max_chars, chunks = self.content_chunker.should_chunk_content(
                content_text, chosen_lang
            )

            if should_chunk and self.cfg.openrouter.long_context_model:
                logger.info(
                    "chunking_bypassed_long_context",
                    extra={
                        "cid": correlation_id,
                        "long_context_model": self.cfg.openrouter.long_context_model,
                        "content_length": len(content_text),
                    },
                )
                should_chunk = False
                chunks = None

            # Inform the user how the content will be handled (skip if silent or batch)
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

            logger.info(
                "content_handling",
                extra={
                    "cid": correlation_id,
                    "length": len(content_text),
                    "should_chunk": should_chunk,
                    "chunks": len(chunks) if chunks else 0,
                },
            )

            # Signal phase: analyzing / summarizing content
            if on_phase_change:
                await on_phase_change(
                    "analyzing", title, len(content_text), self.cfg.openrouter.model
                )

            # Process content (either chunked or single)
            summary_json: dict[str, Any] | None
            if should_chunk and chunks:
                summary_json = await self.content_chunker.process_chunks(
                    chunks,
                    system_prompt,
                    chosen_lang,
                    req_id,
                    correlation_id,
                )
                if summary_json:
                    summary_json = await self.llm_summarizer.enrich_summary_rag_fields(
                        summary_json,
                        content_text=content_text,
                        chosen_lang=chosen_lang,
                        req_id=req_id,
                    )
            else:
                summary_json = await self.llm_summarizer.summarize_content(
                    message,
                    content_text,
                    chosen_lang,
                    system_prompt,
                    req_id,
                    max_chars,
                    correlation_id,
                    interaction_id,
                    url_hash=dedupe_hash,
                    url=url_text,
                    silent=notify_silent,
                    on_phase_change=on_phase_change,
                    images=images,
                    progress_tracker=progress_tracker,
                )

            if summary_json is None:
                logger.error(
                    "summarization_failed",
                    extra={"cid": correlation_id, "url": url_text},
                )
                if not silent and not batch_mode:
                    await self.response_formatter.send_error_notification(
                        message,
                        "processing_failed",
                        correlation_id or "unknown",
                    )
                return URLProcessingFlowResult(success=False)

            if should_chunk and chunks:
                persist_task = self._schedule_persistence_task(
                    self._persist_summary(
                        req_id=req_id,
                        chosen_lang=chosen_lang,
                        summary_json=summary_json,
                        correlation_id=correlation_id,
                        interaction_id=interaction_id,
                        silent=silent,
                    ),
                    correlation_id,
                    "persist_summary",
                )
            else:
                persist_task = None

            # Format and send the response (skip if silent or batch)
            if not silent and not batch_mode:
                llm_result = self.llm_summarizer.last_llm_result or self._create_chunk_llm_stub()
                # Pass request ID prefixed with 'req:' for action button callbacks
                await self.response_formatter.send_structured_summary_response(
                    message,
                    summary_json,
                    llm_result,
                    chunks=len(chunks) if should_chunk and chunks else None,
                    summary_id=f"req:{req_id}" if req_id else None,
                    correlation_id=correlation_id,
                )

            # Skip post-summary background tasks in batch mode to reduce noise
            if not batch_mode:
                await self._schedule_post_summary_tasks(
                    message,
                    content_text,
                    chosen_lang,
                    req_id,
                    correlation_id,
                    summary_json,
                    needs_ru_translation=needs_ru_translation,
                    silent=silent,
                    url_hash=dedupe_hash,
                )

            # For silent or batch mode, we need to ensure persistence completes
            if (silent or batch_mode) and persist_task:
                await self._await_persistence_task(persist_task)

            # Return result with extracted title
            return URLProcessingFlowResult.from_summary(summary_json)

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

    async def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt for the given language.

        This is an async wrapper around the module-level _get_system_prompt function.
        """
        return _get_system_prompt(lang)

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
            norm = normalize_url(url_text)
            dedupe_hash = url_hash_sha256(norm)

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
                        self._create_chunk_llm_stub(),
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
                return URLProcessingFlowResult.from_summary(payload, cached=True)
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
            self._schedule_background_task(
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

        self._schedule_background_task(
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
                    self._schedule_background_task(
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
