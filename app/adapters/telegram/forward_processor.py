"""Refactored forward processor using modular components."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine, Mapping
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.adapters.telegram.forward_summarizer import ForwardSummarizer
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue

logger = logging.getLogger(__name__)

# Background tasks (article generation, insights) are killed after this timeout
# to prevent hung LLM calls from accumulating indefinitely.
_BACKGROUND_TASK_TIMEOUT_SEC = 300


class ForwardProcessor:
    """Refactored forward processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
        db_write_queue: DbWriteQueue | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self._db_write_queue = db_write_queue
        self._llm_summarizer: Any | None = None

        # Initialize components
        self.content_processor = ForwardContentProcessor(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            audit_func=audit_func,
        )

        self.summarizer = ForwardSummarizer(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            db_write_queue=db_write_queue,
        )

    async def handle_forward_flow(
        self, message: Any, *, correlation_id: str | None = None, interaction_id: int | None = None
    ) -> None:
        """Handle complete forwarded message processing flow."""
        try:
            # Process forward content
            (
                req_id,
                prompt,
                chosen_lang,
                system_prompt,
            ) = await self.content_processor.process_forward_content(message, correlation_id)

            if await self._maybe_reply_with_cached_summary(
                message,
                req_id,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            ):
                return

            # Summarize content
            forward_shaped = await self.summarizer.summarize_forward(
                message, prompt, chosen_lang, system_prompt, req_id, correlation_id, interaction_id
            )

            if forward_shaped:
                # Send formatted preview for forward flow with action buttons
                await self.response_formatter.send_forward_summary_response(
                    message,
                    forward_shaped,
                    summary_id=f"req:{req_id}" if req_id else None,
                )

                summary_payload: dict[str, Any] | None = (
                    dict(forward_shaped) if isinstance(forward_shaped, dict) else None
                )

                self._schedule_background_task(
                    self._maybe_generate_custom_article(
                        message,
                        summary_payload,
                        chosen_lang,
                        req_id,
                        correlation_id,
                    ),
                    correlation_id,
                    "custom_article_forward",
                )

                self._schedule_background_task(
                    self._run_forward_insights(
                        message,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary_payload,
                    ),
                    correlation_id,
                    "additional_insights_forward",
                )

        except Exception as e:
            logger.exception("forward_flow_error", extra={"error": str(e), "cid": correlation_id})
            try:
                await self.response_formatter.send_error_notification(
                    message,
                    "processing_failed",
                    correlation_id or "unknown",
                )
            except Exception:
                logger.debug(
                    "forward_flow_error_notification_failed", extra={"cid": correlation_id}
                )

    def _schedule_background_task(
        self, coro: Coroutine[Any, Any, Any], correlation_id: str | None, label: str
    ) -> asyncio.Task[Any] | None:
        async def _with_timeout() -> Any:
            try:
                return await asyncio.wait_for(coro, timeout=_BACKGROUND_TASK_TIMEOUT_SEC)
            except TimeoutError:
                logger.warning(
                    "background_task_timeout",
                    extra={
                        "cid": correlation_id,
                        "label": label,
                        "timeout_sec": _BACKGROUND_TASK_TIMEOUT_SEC,
                    },
                )
                return None

        try:
            task: asyncio.Task[Any] = asyncio.create_task(_with_timeout())
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
                logger.warning(
                    "background_task_failed",
                    extra={"cid": correlation_id, "label": label, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

    async def _run_forward_insights(
        self,
        message: Any,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        summary_payload: dict[str, Any] | None,
    ) -> None:
        content_text = await self._get_forward_content_text(message, req_id)
        if not content_text:
            return
        await self._handle_additional_insights(
            message,
            content_text,
            chosen_lang,
            req_id,
            correlation_id,
            summary=summary_payload,
        )

    async def _maybe_reply_with_cached_summary(
        self,
        message: Any,
        req_id: int,
        *,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> bool:
        """Return True if a cached summary exists for the forward request."""
        summary_row = await self.summary_repo.async_get_summary_by_request(req_id)
        if not summary_row:
            return False

        payload = summary_row.get("json_payload")
        if not payload:
            return False

        try:
            shaped = json.loads(payload)
        except json.JSONDecodeError:
            return False

        await self.response_formatter.send_cached_summary_notification(message)
        await self.response_formatter.send_forward_summary_response(
            message,
            shaped,
            summary_id=f"req:{req_id}" if req_id else None,
        )

        await self.request_repo.async_update_request_status(req_id, "ok")

        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=logger,
            )

        self._audit(
            "INFO",
            "forward_summary_cache_hit",
            {"request_id": req_id, "cid": correlation_id},
        )
        return True

    async def _get_forward_content_text(self, message: Any, req_id: int) -> str | None:
        """Extract the content text for a forward message from the requests table."""
        try:
            request_row = await self.request_repo.async_get_request_by_id(req_id)
            if not request_row:
                return None

            content_text = request_row.get("content_text")
            if isinstance(content_text, str):
                return content_text

            return None
        except Exception as exc:
            logger.exception(
                "get_forward_content_text_failed",
                extra={"error": str(exc), "req_id": req_id},
            )
            return None

    def _get_llm_summarizer(self) -> Any:
        """Lazily create a shared LLMSummarizer for background tasks."""
        if self._llm_summarizer is None:
            from app.adapters.content.llm_summarizer import LLMSummarizer

            self._llm_summarizer = LLMSummarizer(
                cfg=self.cfg,
                db=self.db,
                openrouter=self.summarizer.openrouter,
                response_formatter=self.response_formatter,
                audit_func=self._audit,
                sem=self._sem,
                db_write_queue=self._db_write_queue,
            )
        return self._llm_summarizer

    async def _maybe_generate_custom_article(
        self,
        message: Any,
        summary: dict[str, Any] | None,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
    ) -> None:
        """Generate a standalone article for forwarded content when topics are present."""
        if not summary:
            return

        topics_raw = summary.get("key_ideas") if isinstance(summary, Mapping) else None
        tags_raw = summary.get("topic_tags") if isinstance(summary, Mapping) else None

        topics = [str(item).strip() for item in (topics_raw or []) if str(item).strip()]
        tags = [str(item).strip() for item in (tags_raw or []) if str(item).strip()]

        if not topics and not tags:
            return

        logger.info(
            "custom_article_flow_started_for_forward",
            extra={
                "cid": correlation_id,
                "topics_count": len(topics),
                "tags_count": len(tags),
            },
        )

        from app.core.async_utils import raise_if_cancelled

        llm_summarizer = self._get_llm_summarizer()

        try:
            await self.response_formatter.safe_reply(
                message,
                "📝 Crafting a standalone article from topics & tags…",
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.debug(
                "forward_custom_article_notice_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )

        article = await llm_summarizer.generate_custom_article(
            message,
            chosen_lang=chosen_lang,
            req_id=req_id,
            topics=topics,
            tags=tags,
            correlation_id=correlation_id,
        )

        if article:
            await self.response_formatter.send_custom_article(message, article)
            logger.info(
                "custom_article_sent_for_forward",
                extra={"cid": correlation_id, "has_article": True},
            )
        else:
            logger.debug(
                "custom_article_not_generated_for_forward",
                extra={"cid": correlation_id},
            )

    async def _handle_additional_insights(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Generate and persist additional insights using the LLM."""
        logger.info(
            "insights_flow_started_for_forward",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            summary_payload: dict[str, Any] | None = None
            if isinstance(summary, Mapping):
                summary_payload = dict(summary)
            if summary_payload is None:
                try:
                    row = await self.summary_repo.async_get_summary_by_request(req_id)
                    json_payload = row.get("json_payload") if row else None
                    if json_payload:
                        summary_payload = json.loads(json_payload)
                except Exception as exc:
                    logger.debug(
                        "forward_insights_summary_load_failed",
                        extra={"cid": correlation_id, "error": str(exc)},
                    )

            llm_summarizer = self._get_llm_summarizer()

            insights = await llm_summarizer.generate_additional_insights(
                message,
                content_text=content_text,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                summary=summary_payload,
            )

            if insights:
                logger.info(
                    "insights_generated_successfully_for_forward",
                    extra={
                        "cid": correlation_id,
                        "facts_count": len(insights.get("new_facts", [])),
                        "has_overview": bool(insights.get("topic_overview")),
                    },
                )

                await self.response_formatter.send_additional_insights_message(
                    message, insights, correlation_id
                )

                logger.info("insights_message_sent_for_forward", extra={"cid": correlation_id})

                try:
                    await self.summary_repo.async_update_summary_insights(req_id, insights)
                    logger.debug(
                        "insights_persisted_for_forward",
                        extra={"cid": correlation_id, "request_id": req_id},
                    )
                except Exception as exc:
                    logger.exception(
                        "persist_insights_error_for_forward",
                        extra={"cid": correlation_id, "error": str(exc)},
                    )
            else:
                logger.warning(
                    "insights_generation_returned_empty_for_forward",
                    extra={"cid": correlation_id, "reason": "LLM returned None or empty insights"},
                )

        except Exception as exc:
            logger.exception(
                "insights_flow_error_for_forward",
                extra={"cid": correlation_id, "error": str(exc)},
            )
