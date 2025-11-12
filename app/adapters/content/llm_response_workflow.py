"""Reusable workflow helper for handling LLM summary responses."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.json_utils import extract_json
from app.core.summary_contract import validate_and_shape_summary
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction
from app.utils.json_validation import finalize_summary_texts, parse_summary_response

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMRequestConfig:
    """Configuration for a single LLM attempt."""

    messages: list[dict[str, Any]]
    response_format: dict[str, Any]
    max_tokens: int | None
    temperature: float | None
    top_p: float | None
    model_override: str | None = None
    silent: bool = False


@dataclass(slots=True)
class LLMRepairContext:
    """Context required to attempt JSON repair prompts."""

    base_messages: list[dict[str, Any]]
    repair_response_format: dict[str, Any]
    repair_max_tokens: int | None
    default_prompt: str
    missing_fields_prompt: str | None = None


@dataclass(slots=True)
class LLMWorkflowNotifications:
    """Notification callbacks invoked during workflow progression."""

    completion: Callable[[Any, LLMRequestConfig], Awaitable[None]] | None = None
    llm_error: Callable[[Any, str | None], Awaitable[None]] | None = None
    repair_failure: Callable[[], Awaitable[None]] | None = None
    parsing_failure: Callable[[], Awaitable[None]] | None = None


@dataclass(slots=True)
class LLMInteractionConfig:
    """Settings for updating user interactions."""

    interaction_id: int | None
    success_kwargs: dict[str, Any] | None = None
    llm_error_builder: Callable[[Any, str | None], dict[str, Any]] | None = None
    repair_failure_kwargs: dict[str, Any] | None = None
    parsing_failure_kwargs: dict[str, Any] | None = None


@dataclass(slots=True)
class LLMSummaryPersistenceSettings:
    """Configuration for persisting summary results."""

    lang: str
    is_read: bool = True
    insights_getter: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


class LLMResponseWorkflow:
    """Reusable helper encapsulating shared LLM response automation."""

    def __init__(
        self,
        *,
        cfg: Any,
        db: Database,
        openrouter: Any,
        response_formatter: Any,
        audit_func: Callable[[str, str, dict[str, Any]], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem

    async def execute_summary_workflow(
        self,
        *,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        persistence: LLMSummaryPersistenceSettings,
        repair_context: LLMRepairContext,
        requests: Sequence[LLMRequestConfig],
        notifications: LLMWorkflowNotifications | None = None,
        ensure_summary: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        on_attempt: Callable[[Any], Awaitable[None]] | None = None,
        on_success: Callable[[dict[str, Any], Any], Awaitable[None]] | None = None,
        required_summary_fields: Sequence[str] = ("tldr", "summary_250", "summary_1000"),
    ) -> dict[str, Any] | None:
        """Run the shared summary processing workflow for a sequence of attempts."""

        if not requests:
            raise ValueError("requests must include at least one attempt")

        # Track all failed attempts for final error reporting
        failed_attempts: list[tuple[Any, LLMRequestConfig]] = []
        total_attempts = len(requests)

        for attempt_index, attempt in enumerate(requests):
            is_last_attempt = attempt_index == total_attempts - 1

            llm = await self._invoke_llm(attempt, req_id)

            if on_attempt is not None:
                await on_attempt(llm)

            await self._persist_llm_call(llm, req_id, correlation_id)

            # Only send completion notifications for successful attempts or the last attempt
            if notifications and notifications.completion and (llm.status == "ok" or is_last_attempt):
                await notifications.completion(llm, attempt)

            summary = await self._process_attempt(
                message=message,
                llm=llm,
                req_id=req_id,
                correlation_id=correlation_id,
                interaction_config=interaction_config,
                persistence=persistence,
                repair_context=repair_context,
                request_config=attempt,
                notifications=notifications,
                ensure_summary=ensure_summary,
                on_success=on_success,
                required_summary_fields=required_summary_fields,
                is_last_attempt=is_last_attempt,
                failed_attempts=failed_attempts,
            )

            if summary is not None:
                return summary

            # Track failed attempt for final error reporting
            if llm.status != "ok":
                failed_attempts.append((llm, attempt))

        # All attempts failed - send consolidated error notification
        await self._handle_all_attempts_failed(
            message,
            req_id,
            correlation_id,
            interaction_config,
            notifications,
            failed_attempts,
        )
        return None

    def build_structured_response_format(self, mode: str | None = None) -> dict[str, Any]:
        """Build response format configuration for structured outputs."""
        try:
            from app.core.summary_contract import get_summary_json_schema

            current_mode = mode or self.cfg.openrouter.structured_output_mode

            if current_mode == "json_schema":
                return {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "summary_schema",
                        "schema": get_summary_json_schema(),
                        "strict": True,
                    },
                }
            return {"type": "json_object"}
        except Exception:
            return {"type": "json_object"}

    async def persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        """Public helper to persist an LLM call."""

        await self._persist_llm_call(llm, req_id, correlation_id)

    async def _invoke_llm(self, request: LLMRequestConfig, req_id: int) -> Any:
        async with self._sem():
            return await self.openrouter.chat(
                request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                request_id=req_id,
                response_format=request.response_format,
                model_override=request.model_override,
            )

    async def _process_attempt(
        self,
        *,
        message: Any,
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        persistence: LLMSummaryPersistenceSettings,
        repair_context: LLMRepairContext,
        request_config: LLMRequestConfig,
        notifications: LLMWorkflowNotifications | None,
        ensure_summary: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None,
        on_success: Callable[[dict[str, Any], Any], Awaitable[None]] | None,
        required_summary_fields: Sequence[str],
        is_last_attempt: bool = False,
        failed_attempts: list[tuple[Any, LLMRequestConfig]] | None = None,
    ) -> dict[str, Any] | None:
        if llm.status != "ok":
            salvage = None
            if (llm.error_text or "") == "structured_output_parse_error":
                salvage = await self._attempt_salvage_parsing(llm, correlation_id)
            if salvage is not None:
                return await self._finalize_success(
                    salvage,
                    llm,
                    req_id,
                    correlation_id,
                    interaction_config,
                    persistence,
                    ensure_summary,
                    on_success,
                )

            # Only handle LLM error immediately if this is the last attempt
            # Otherwise, we'll batch all errors and report once at the end
            if is_last_attempt:
                await self._handle_llm_error(
                    message,
                    llm,
                    req_id,
                    correlation_id,
                    interaction_config,
                    notifications,
                    is_final_error=True,
                )
            else:
                # Just update database status, don't send notifications yet
                await self.db.async_update_request_status(req_id, "error")
            return None

        parse_result = parse_summary_response(llm.response_json, llm.response_text)
        shaped = parse_result.shaped if parse_result else None

        if shaped is None:
            shaped = await self._attempt_json_repair(
                message,
                llm,
                req_id,
                correlation_id,
                interaction_config,
                repair_context,
                request_config,
                notifications,
                parse_result=parse_result,
            )

        if shaped is None:
            return None

        finalize_summary_texts(shaped)

        if not self._summary_has_content(shaped, required_summary_fields):
            logger.warning(
                "summary_fields_empty",
                extra={"cid": correlation_id, "stage": "attempt"},
            )
            return None

        return await self._finalize_success(
            shaped,
            llm,
            req_id,
            correlation_id,
            interaction_config,
            persistence,
            ensure_summary,
            on_success,
        )

    async def _finalize_success(
        self,
        summary: dict[str, Any],
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        persistence: LLMSummaryPersistenceSettings,
        ensure_summary: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None,
        on_success: Callable[[dict[str, Any], Any], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        if ensure_summary is not None:
            summary = await ensure_summary(summary)

        finalize_summary_texts(summary)

        if on_success is not None:
            await on_success(summary, llm)

        insights_json: dict[str, Any] | None = None
        if persistence.insights_getter is not None:
            try:
                insights_json = persistence.insights_getter(summary)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "insights_getter_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

        try:
            new_version = await self.db.async_upsert_summary(
                request_id=req_id,
                lang=persistence.lang,
                json_payload=summary,
                insights_json=insights_json,
                is_read=persistence.is_read,
            )
            await self.db.async_update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "persist_summary_error",
                extra={"error": str(exc), "cid": correlation_id},
            )

        if interaction_config.interaction_id and interaction_config.success_kwargs:
            try:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **interaction_config.success_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
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

    async def _attempt_salvage_parsing(
        self, llm: Any, correlation_id: str | None
    ) -> dict[str, Any] | None:
        try:
            parsed = extract_json(llm.response_text or "")
            if isinstance(parsed, dict):
                shaped = validate_and_shape_summary(parsed)
                finalize_summary_texts(shaped)
                if shaped:
                    return shaped

            parse_result = parse_summary_response(llm.response_json, llm.response_text)
            shaped = parse_result.shaped if parse_result else None
            if shaped:
                finalize_summary_texts(shaped)
                logger.info(
                    "structured_output_salvage_success",
                    extra={"cid": correlation_id},
                )
                return shaped
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "salvage_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
        return None

    async def _attempt_json_repair(
        self,
        message: Any,
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        repair_context: LLMRepairContext,
        request_config: LLMRequestConfig,
        notifications: LLMWorkflowNotifications | None,
        *,
        parse_result: Any,
    ) -> dict[str, Any] | None:
        try:
            logger.info(
                "json_repair_attempt_enhanced",
                extra={
                    "cid": correlation_id,
                    "reason": (
                        parse_result.errors[-3:] if parse_result and parse_result.errors else None
                    ),
                    "structured_mode": self.cfg.openrouter.structured_output_mode,
                },
            )

            repair_messages = list(repair_context.base_messages)
            repair_messages.append({"role": "assistant", "content": llm.response_text or ""})

            if (
                parse_result
                and parse_result.errors
                and "missing_summary_fields" in parse_result.errors
            ):
                prompt = repair_context.missing_fields_prompt or repair_context.default_prompt
            else:
                prompt = repair_context.default_prompt

            repair_messages.append({"role": "user", "content": prompt})

            async with self._sem():
                repair = await self.openrouter.chat(
                    repair_messages,
                    temperature=request_config.temperature,
                    max_tokens=repair_context.repair_max_tokens,
                    top_p=request_config.top_p,
                    request_id=req_id,
                    response_format=repair_context.repair_response_format,
                    model_override=request_config.model_override,
                )

            if repair.status == "ok":
                repair_result = parse_summary_response(repair.response_json, repair.response_text)
                if repair_result.shaped is not None:
                    finalize_summary_texts(repair_result.shaped)
                    logger.info(
                        "json_repair_success_enhanced",
                        extra={
                            "cid": correlation_id,
                            "used_local_fix": repair_result.used_local_fix,
                        },
                    )
                    return repair_result.shaped
                raise ValueError("repair_failed")
            raise ValueError("repair_call_error")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "json_repair_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            await self._handle_repair_failure(
                message,
                req_id,
                correlation_id,
                interaction_config,
                notifications,
            )
            return None

    async def _handle_llm_error(
        self,
        message: Any,
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        notifications: LLMWorkflowNotifications | None,
        is_final_error: bool = False,
    ) -> None:
        await self.db.async_update_request_status(req_id, "error")

        error_parts: list[str] = []
        context = getattr(llm, "error_context", None) or {}

        status_code = context.get("status_code") if isinstance(context, dict) else None
        if status_code is not None:
            error_parts.append(f"HTTP {status_code}")

        message_text = context.get("message") if isinstance(context, dict) else None
        if message_text:
            error_parts.append(str(message_text))

        api_error = context.get("api_error") if isinstance(context, dict) else None
        if api_error and api_error not in error_parts:
            error_parts.append(str(api_error))

        provider = context.get("provider") if isinstance(context, dict) else None
        if provider:
            error_parts.append(f"Provider: {provider}")

        if llm.error_text and llm.error_text not in error_parts:
            error_parts.append(str(llm.error_text))

        error_details = " | ".join(error_parts) if error_parts else None

        logger.error(
            "openrouter_error",
            extra={"error": llm.error_text, "cid": correlation_id},
        )

        try:
            self._audit(
                "ERROR",
                "openrouter_error",
                {"request_id": req_id, "cid": correlation_id, "error": llm.error_text},
            )
        except Exception:
            pass

        # Only send notifications if this is the final error
        if is_final_error and notifications and notifications.llm_error:
            try:
                await notifications.llm_error(llm, error_details)
            except Exception:
                pass

        if interaction_config.interaction_id and interaction_config.llm_error_builder:
            try:
                kwargs = interaction_config.llm_error_builder(llm, error_details)
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "interaction_error_update_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

    async def _handle_repair_failure(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        notifications: LLMWorkflowNotifications | None,
    ) -> None:
        await self.db.async_update_request_status(req_id, "error")

        if notifications and notifications.repair_failure:
            try:
                await notifications.repair_failure()
            except Exception:
                pass

        if interaction_config.interaction_id and interaction_config.repair_failure_kwargs:
            try:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **interaction_config.repair_failure_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "interaction_repair_update_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

    async def _handle_parsing_failure(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        notifications: LLMWorkflowNotifications | None,
    ) -> None:
        await self.db.async_update_request_status(req_id, "error")

        if notifications and notifications.parsing_failure:
            try:
                await notifications.parsing_failure()
            except Exception:
                pass

        if interaction_config.interaction_id and interaction_config.parsing_failure_kwargs:
            try:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **interaction_config.parsing_failure_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "interaction_parsing_update_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

    async def _handle_all_attempts_failed(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        notifications: LLMWorkflowNotifications | None,
        failed_attempts: list[tuple[Any, LLMRequestConfig]],
    ) -> None:
        """Handle the case when all LLM attempts have failed."""
        await self.db.async_update_request_status(req_id, "error")

        # Collect error details from all failed attempts
        error_details_list: list[str] = []
        models_tried: list[str] = []

        for llm, config in failed_attempts:
            model_name = config.model_override or llm.model or "unknown"
            models_tried.append(model_name)

            context = getattr(llm, "error_context", None) or {}

            # Build error parts for this attempt
            error_parts: list[str] = []
            status_code = context.get("status_code") if isinstance(context, dict) else None
            if status_code is not None:
                error_parts.append(f"HTTP {status_code}")

            message_text = context.get("message") if isinstance(context, dict) else None
            if message_text:
                error_parts.append(str(message_text))

            if llm.error_text and llm.error_text not in error_parts:
                error_parts.append(str(llm.error_text))

            if error_parts:
                error_details_list.append(" | ".join(error_parts))

        # Use the most recent error details
        final_error_details = error_details_list[-1] if error_details_list else None

        # Build comprehensive error message
        comprehensive_details = f"Tried {len(failed_attempts)} model(s): {', '.join(models_tried)}"
        if final_error_details:
            comprehensive_details += f"\n🔍 Last error: {final_error_details}"

        logger.error(
            "all_llm_attempts_failed",
            extra={
                "error": final_error_details,
                "cid": correlation_id,
                "models_tried": models_tried,
                "total_attempts": len(failed_attempts),
            },
        )

        try:
            self._audit(
                "ERROR",
                "all_llm_attempts_failed",
                {
                    "request_id": req_id,
                    "cid": correlation_id,
                    "models_tried": models_tried,
                    "error": final_error_details,
                },
            )
        except Exception:
            pass

        # Send a single consolidated error notification
        if notifications and notifications.llm_error:
            try:
                await notifications.llm_error(
                    failed_attempts[-1][0] if failed_attempts else None,
                    comprehensive_details,
                )
            except Exception:
                pass

        if interaction_config.interaction_id and interaction_config.llm_error_builder:
            try:
                last_llm = failed_attempts[-1][0] if failed_attempts else None
                kwargs = interaction_config.llm_error_builder(last_llm, comprehensive_details)
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_config.interaction_id,
                    logger_=logger,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "interaction_error_update_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

    def _summary_has_content(self, summary: dict[str, Any], required_fields: Sequence[str]) -> bool:
        for field in required_fields:
            value = summary.get(field)
            if isinstance(value, str) and value.strip():
                return True
        return False

    async def _persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        try:
            await self.db.async_insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=llm.request_headers or {},
                request_messages_json=list(llm.request_messages or []),
                response_text=llm.response_text,
                response_json=llm.response_json or {},
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
                structured_output_used=getattr(llm, "structured_output_used", None),
                structured_output_mode=getattr(llm, "structured_output_mode", None),
                error_context_json=(
                    getattr(llm, "error_context", {})
                    if getattr(llm, "error_context", None) is not None
                    else None
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "persist_llm_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
