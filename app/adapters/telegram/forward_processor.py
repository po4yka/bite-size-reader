"""Refactored forward processor using modular components."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.adapters.telegram.forward_summarizer import ForwardSummarizer
from app.config import AppConfig
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


class ForwardProcessor:
    """Refactored forward processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func

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
                # Send formatted preview for forward flow
                await self.response_formatter.send_forward_summary_response(message, forward_shaped)

                # Generate and send additional research insights (same as URL processing)
                try:
                    # Get the content text from the content processor
                    content_text = await self._get_forward_content_text(message, req_id)
                    if content_text:
                        await self._handle_additional_insights(
                            message,
                            content_text,
                            chosen_lang,
                            req_id,
                            correlation_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "insights_generation_failed_for_forward",
                        extra={"error": str(exc), "cid": correlation_id, "req_id": req_id},
                    )

        except Exception as e:
            # Handle unexpected errors
            logger.exception("forward_flow_error", extra={"error": str(e), "cid": correlation_id})

    async def _maybe_reply_with_cached_summary(
        self,
        message: Any,
        req_id: int,
        *,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> bool:
        """Return True if a cached summary exists for the forward request."""
        summary_row = self.db.get_summary_by_request(req_id)
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
        await self.response_formatter.send_forward_summary_response(message, shaped)

        self.db.update_request_status(req_id, "ok")

        if interaction_id:
            self.summarizer._update_user_interaction(  # noqa: SLF001
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

        self._audit(
            "INFO",
            "forward_summary_cache_hit",
            {"request_id": req_id, "cid": correlation_id},
        )
        return True

    async def _get_forward_content_text(self, message: Any, req_id: int) -> str | None:
        """Extract the content text for a forward message."""
        try:
            # Get the request details to extract the content
            request_row = self.db.get_summary_by_request(req_id)
            if not request_row:
                return None

            # If no summary found, try to get from request directly
            content_text = request_row.get("content_text")
            if isinstance(content_text, str):
                return content_text

            # Fallback: get from request table directly
            # Since we don't have get_request_by_id, we'll need to construct a query
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT content_text FROM requests WHERE id = ?", (req_id,)
                ).fetchone()
                if row:
                    return row[0]
            return None
        except Exception as exc:
            logger.error(
                "get_forward_content_text_failed",
                extra={"error": str(exc), "req_id": req_id},
            )
            return None

    async def _handle_additional_insights(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
    ) -> None:
        """Generate and persist additional insights using the LLM."""
        logger.info(
            "insights_flow_started_for_forward",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            from app.adapters.content.llm_summarizer import LLMSummarizer

            # Create LLMSummarizer instance with same dependencies as ForwardSummarizer
            summary_payload: dict[str, Any] | None = None
            try:
                row = self.db.get_summary_by_request(req_id)
                json_payload = row.get("json_payload") if row else None
                if json_payload:
                    summary_payload = json.loads(json_payload)
            except Exception as exc:
                logger.debug(
                    "forward_insights_summary_load_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

            llm_summarizer = LLMSummarizer(
                cfg=self.cfg,
                db=self.db,
                openrouter=self.summarizer.openrouter,
                response_formatter=self.response_formatter,
                audit_func=self._audit,
                sem=self.summarizer._sem,
            )

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
                    self.db.update_summary_insights(req_id, insights)
                    logger.debug(
                        "insights_persisted_for_forward",
                        extra={"cid": correlation_id, "request_id": req_id},
                    )
                except Exception as exc:
                    logger.error(
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
