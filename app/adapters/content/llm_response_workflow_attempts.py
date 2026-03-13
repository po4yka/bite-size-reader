"""Attempt/finalization mixin for LLM response workflow."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled
from app.db.user_interactions import async_safe_update_user_interaction
from app.utils.json_validation import finalize_summary_texts

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.adapters.content.llm_response_workflow import AttemptContext

logger = logging.getLogger("app.adapters.content.llm_response_workflow")


class LLMWorkflowAttemptsMixin:
    """Per-attempt processing, summary finalization, and persistence."""

    # Explicit host contract for composition with LLMResponseWorkflow.
    _attempt_json_repair: Callable[..., Any]
    _attempt_salvage_parsing: Callable[..., Any]
    _audit: Callable[..., None]
    _handle_llm_error: Callable[..., Any]
    _schedule_background_task: Callable[..., Any]
    cfg: Any
    request_repo: Any
    summary_repo: Any
    user_repo: Any

    async def _process_attempt(self, ctx: AttemptContext) -> dict[str, Any] | None:
        """Process a single LLM attempt using a typed context bundle."""
        if ctx.llm.status != "ok":
            salvage = None
            if (ctx.llm.error_text or "") == "structured_output_parse_error":
                salvage = await self._attempt_salvage_parsing(ctx.llm, ctx.correlation_id)
            if salvage is not None:
                return await self._finalize_success(
                    salvage,
                    ctx.llm,
                    ctx.req_id,
                    ctx.correlation_id,
                    ctx.interaction_config,
                    ctx.persistence,
                    ctx.ensure_summary,
                    ctx.on_success,
                    ctx.defer_persistence,
                )

            if ctx.is_last_attempt:
                await self._handle_llm_error(
                    ctx.message,
                    ctx.llm,
                    ctx.req_id,
                    ctx.correlation_id,
                    ctx.interaction_config,
                    ctx.notifications,
                    is_final_error=True,
                )
            else:
                await self.request_repo.async_update_request_status(ctx.req_id, "error")
            return None

        json_parse_timeout = getattr(self.cfg.runtime, "json_parse_timeout_sec", 60.0)
        try:
            from app.adapters.content import llm_response_workflow as workflow_module

            async with asyncio.timeout(json_parse_timeout):
                parse_result = await asyncio.to_thread(
                    workflow_module.parse_summary_response,
                    ctx.llm.response_json,
                    ctx.llm.response_text,
                )
        except TimeoutError:
            logger.error(
                "json_parse_timeout",
                extra={"cid": ctx.correlation_id, "timeout_sec": json_parse_timeout},
            )
            self._set_failure_context(ctx.llm, "json_parse_timeout")
            return None
        shaped = parse_result.shaped if parse_result else None

        if shaped is None:
            shaped = await self._attempt_json_repair(
                ctx.message,
                ctx.llm,
                ctx.req_id,
                ctx.correlation_id,
                ctx.interaction_config,
                ctx.repair_context,
                ctx.request_config,
                ctx.notifications,
                parse_result=parse_result,
            )

        if shaped is None:
            self._set_failure_context(ctx.llm, "summary_parse_failed")
            return None

        finalize_summary_texts(shaped)

        if not self._summary_has_content(shaped, ctx.required_summary_fields):
            logger.warning(
                "summary_fields_empty",
                extra={
                    "cid": ctx.correlation_id,
                    "stage": "attempt",
                    "preset": ctx.request_config.preset_name,
                    "model": ctx.request_config.model_override,
                },
            )

            try:
                repair_hint = SimpleNamespace(errors=["missing_summary_fields"])
                repaired = await self._attempt_json_repair(
                    ctx.message,
                    ctx.llm,
                    ctx.req_id,
                    ctx.correlation_id,
                    ctx.interaction_config,
                    ctx.repair_context,
                    ctx.request_config,
                    ctx.notifications,
                    parse_result=repair_hint,
                )
                if repaired and self._summary_has_content(repaired, ctx.required_summary_fields):
                    return await self._finalize_success(
                        repaired,
                        ctx.llm,
                        ctx.req_id,
                        ctx.correlation_id,
                        ctx.interaction_config,
                        ctx.persistence,
                        ctx.ensure_summary,
                        ctx.on_success,
                        ctx.defer_persistence,
                    )
            except Exception as exc:
                logger.warning(
                    "summary_repair_failed",
                    extra={"cid": ctx.correlation_id, "error": str(exc)},
                )

            self._set_failure_context(ctx.llm, "summary_fields_empty")
            return None

        return await self._finalize_success(
            shaped,
            ctx.llm,
            ctx.req_id,
            ctx.correlation_id,
            ctx.interaction_config,
            ctx.persistence,
            ctx.ensure_summary,
            ctx.on_success,
            ctx.defer_persistence,
        )

    async def _finalize_success(
        self,
        summary: dict[str, Any],
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: Any,
        persistence: Any,
        ensure_summary: Any | None,
        on_success: Any | None,
        defer_persistence: bool,
    ) -> dict[str, Any]:
        from app.adapters.external.formatting.data_formatter import DataFormatterImpl

        formatter = DataFormatterImpl()
        summary = formatter.normalize_metric_names(summary)

        if ensure_summary is not None:
            summary = await ensure_summary(summary)

        finalize_summary_texts(summary)

        if on_success is not None:
            await on_success(summary, llm)

        insights_json: dict[str, Any] | None = None
        if persistence.insights_getter is not None:
            try:
                insights_json = persistence.insights_getter(summary)
            except Exception as exc:
                logger.exception(
                    "insights_getter_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

        if defer_persistence or persistence.defer_write:
            self._schedule_background_task(
                self._persist_summary(
                    req_id=req_id,
                    persistence=persistence,
                    summary=summary,
                    insights_json=insights_json,
                    correlation_id=correlation_id,
                ),
                "persist_summary",
                correlation_id,
            )
        else:
            await self._persist_summary(
                req_id=req_id,
                persistence=persistence,
                summary=summary,
                insights_json=insights_json,
                correlation_id=correlation_id,
            )

        if interaction_config.interaction_id and interaction_config.success_kwargs:
            try:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **interaction_config.success_kwargs,
                )
            except Exception as exc:
                logger.exception(
                    "interaction_success_update_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

        logger.info(
            "llm_finished_enhanced",
            extra={
                "status": llm.status,
                "latency_ms": llm.latency_ms,
                "model": llm.model,
                "cid": correlation_id,
                "summary_250_len": len(summary.get("summary_250", "")),
                "tldr_len": len(summary.get("tldr", "") or summary.get("summary_1000", "")),
                "key_ideas_count": len(summary.get("key_ideas", [])),
                "topic_tags_count": len(summary.get("topic_tags", [])),
                "entities_count": len(summary.get("entities", [])),
                "reading_time_min": summary.get("estimated_reading_time_min"),
                "seo_keywords_count": len(summary.get("seo_keywords", [])),
                "structured_output_used": getattr(llm, "structured_output_used", False),
                "structured_output_mode": getattr(llm, "structured_output_mode", None),
            },
        )

        return summary

    async def _persist_summary(
        self,
        *,
        req_id: int,
        persistence: Any,
        summary: dict[str, Any],
        insights_json: dict[str, Any] | None,
        correlation_id: str | None,
    ) -> None:
        try:
            new_version = await self.summary_repo.async_finalize_request_summary(
                request_id=req_id,
                lang=persistence.lang,
                json_payload=summary,
                insights_json=insights_json,
                is_read=persistence.is_read,
            )
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as exc:
            logger.exception(
                "persist_summary_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
            raise

    def _summary_has_content(self, summary: dict[str, Any], required_fields: Sequence[str]) -> bool:
        for field in required_fields:
            value = summary.get(field)
            if isinstance(value, str) and value.strip():
                return True
        return False

    def _set_failure_context(self, llm: Any, reason: str) -> None:
        """Attach a human-readable failure reason to an LLM attempt."""
        try:
            if not getattr(llm, "error_text", None):
                llm.error_text = reason
        except Exception as exc:
            raise_if_cancelled(exc)

        try:
            context = getattr(llm, "error_context", None)
            if context is None:
                llm.error_context = {"message": reason}
            elif isinstance(context, dict):
                context.setdefault("message", reason)
                llm.error_context = context
        except Exception as exc:
            raise_if_cancelled(exc)
