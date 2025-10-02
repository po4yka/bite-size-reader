"""Refactored forward processor using modular components."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.adapters.telegram.forward_summarizer import ForwardSummarizer
from app.config import AppConfig
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction

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

                summary_payload: dict[str, Any] | None = (
                    dict(forward_shaped) if isinstance(forward_shaped, dict) else None
                )

                # Generate a standalone article similar to the URL flow
                try:
                    await self._maybe_generate_custom_article(
                        message,
                        summary_payload,
                        chosen_lang,
                        req_id,
                        correlation_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "custom_article_generation_failed_for_forward",
                        extra={"error": str(exc), "cid": correlation_id, "req_id": req_id},
                    )

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
                            summary=summary_payload,
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
        summary_row = await self.db.async_get_summary_by_request(req_id)
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

        await self.db.async_update_request_status(req_id, "ok")

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
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
        """Extract the content text for a forward message."""
        try:
            # Get the request details to extract the content
            request_row = await self.db.async_get_summary_by_request(req_id)
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

        from app.adapters.content.llm_summarizer import LLMSummarizer
        from app.core.async_utils import raise_if_cancelled

        llm_summarizer = LLMSummarizer(
            cfg=self.cfg,
            db=self.db,
            openrouter=self.summarizer.openrouter,
            response_formatter=self.response_formatter,
            audit_func=self._audit,
            sem=self.summarizer._sem,
        )

        try:
            await self.response_formatter.safe_reply(
                message,
                "📝 Crafting a standalone article from topics & tags…",
            )
        except Exception as exc:  # noqa: BLE001
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
            from app.adapters.content.llm_summarizer import LLMSummarizer

            summary_payload: dict[str, Any] | None = None
            if isinstance(summary, Mapping):
                summary_payload = dict(summary)
            if summary_payload is None:
                try:
                    row = await self.db.async_get_summary_by_request(req_id)
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
