"""Post-summary follow-up tasks for URL flows."""

from __future__ import annotations

import logging
from typing import Any

from app.core.async_utils import raise_if_cancelled

logger = logging.getLogger(__name__)


class URLPostSummaryTaskService:
    """Own translation, insights, custom article, and related-reads follow-up work."""

    def __init__(
        self,
        *,
        response_formatter: Any,
        summary_repo: Any,
        article_generator: Any,
        insights_generator: Any,
        summary_delivery: Any,
        related_reads_service: Any | None = None,
    ) -> None:
        self._response_formatter = response_formatter
        self._summary_repo = summary_repo
        self._article_generator = article_generator
        self._insights_generator = insights_generator
        self._summary_delivery = summary_delivery
        self._related_reads_service = related_reads_service
        self._background_tasks: set[Any] = set()

    async def aclose(self, timeout: float = 5.0) -> None:
        """Drain outstanding post-summary background tasks."""
        await self._summary_delivery.drain_tasks(
            self._background_tasks,
            timeout=timeout,
            timeout_event="url_post_summary_shutdown_timeout",
            complete_event="url_post_summary_shutdown_complete",
        )

    async def schedule_tasks(
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
            self._schedule_task(
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
                reader_mode = await self._response_formatter.is_reader_mode(message)
            except Exception:
                reader_mode = False

        if not silent and not reader_mode:
            try:
                await self._response_formatter.safe_reply(
                    message,
                    "🧠 Generating additional research insights…",
                )
            except Exception as exc:
                raise_if_cancelled(exc)

        self._schedule_task(
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
                        await self._response_formatter.safe_reply(
                            message,
                            "📝 Crafting a standalone article from topics & tags…",
                        )
                    except Exception as exc:
                        raise_if_cancelled(exc)

                if not reader_mode:
                    self._schedule_task(
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

        if self._related_reads_service is not None and not silent:
            self._schedule_task(
                self._run_related_reads(
                    message,
                    summary_payload=summary,
                    request_id=req_id,
                    correlation_id=correlation_id,
                    lang=chosen_lang,
                ),
                correlation_id,
                "related_reads",
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
        return await self._article_generator.translate_summary_to_ru(
            summary,
            req_id=req_id,
            correlation_id=correlation_id,
            url_hash=url_hash,
            source_lang=source_lang,
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
        if not needs_translation:
            return

        try:
            translated = await self.translate_summary_to_ru(
                summary,
                req_id=req_id,
                correlation_id=correlation_id,
                url_hash=url_hash,
                source_lang=source_lang,
            )
            if translated:
                await self._response_formatter.send_russian_translation(
                    message,
                    translated,
                    correlation_id=correlation_id,
                )
                return

            await self._response_formatter.safe_reply(
                message,
                (
                    "⚠️ Unable to generate Russian translation right now. Error ID: "
                    f"{correlation_id or 'unknown'}."
                ),
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "ru_translation_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            try:
                await self._response_formatter.safe_reply(
                    message,
                    f"⚠️ Russian translation failed. Error ID: {correlation_id or 'unknown'}.",
                )
            except Exception as reply_exc:
                raise_if_cancelled(reply_exc)

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
        logger.info(
            "insights_flow_started",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            insights = await self._insights_generator.generate_additional_insights(
                message,
                content_text=content_text,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                summary=summary,
                url_hash=url_hash,
            )
            if not insights:
                logger.warning(
                    "insights_generation_returned_empty",
                    extra={"cid": correlation_id, "reason": "LLM returned None or empty insights"},
                )
                return

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
                    should_notify = not (await self._response_formatter.is_reader_mode(message))
                except Exception:
                    should_notify = True

            if should_notify:
                await self._response_formatter.send_additional_insights_message(
                    message,
                    insights,
                    correlation_id,
                )
                logger.info("insights_message_sent", extra={"cid": correlation_id})
            else:
                logger.info(
                    "insights_notification_skipped",
                    extra={"cid": correlation_id, "reason": "reader_mode_or_silent"},
                )

            try:
                await self._summary_repo.async_update_summary_insights(req_id, insights)
                logger.debug(
                    "insights_persisted",
                    extra={"cid": correlation_id, "request_id": req_id},
                )
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.error(
                    "persist_insights_error",
                    extra={"cid": correlation_id, "error": str(exc)},
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
        try:
            article = await self._article_generator.generate_custom_article(
                message,
                chosen_lang=chosen_lang,
                req_id=req_id,
                topics=[str(x) for x in topics if str(x).strip()],
                tags=[str(x) for x in tags if str(x).strip()],
                correlation_id=correlation_id,
                url_hash=url_hash,
            )
            if article:
                await self._response_formatter.send_custom_article(message, article)
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.error(
                "custom_article_flow_error",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def _run_related_reads(
        self,
        message: Any,
        *,
        summary_payload: dict[str, Any],
        request_id: int,
        correlation_id: str | None,
        lang: str,
    ) -> None:
        try:
            items = await self._related_reads_service.find_related(
                summary_payload,
                exclude_request_id=request_id,
            )
            if items:
                await self._response_formatter.send_related_reads(
                    message,
                    items,
                    lang=lang,
                )
        except Exception as exc:
            logger.warning(
                "related_reads_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    def _schedule_task(
        self,
        coro: Any,
        correlation_id: str | None,
        label: str,
    ) -> None:
        self._summary_delivery.schedule_task(
            self._background_tasks,
            coro,
            correlation_id,
            label,
            schedule_error_event="background_task_schedule_failed",
            task_error_event="background_task_failed",
        )
