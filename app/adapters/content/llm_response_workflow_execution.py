"""Execution/lifecycle mixin for LLM response workflow."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled
from app.core.backoff import sleep_backoff

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence

logger = logging.getLogger("app.adapters.content.llm_response_workflow")


class LLMWorkflowExecutionMixin:
    """Workflow execution, retries, and lifecycle helpers."""

    # Explicit host contract for composition with LLMResponseWorkflow.
    _adaptive_timeout: Any
    _background_tasks: set[asyncio.Task[Any]]
    _handle_all_attempts_failed: Callable[..., Any]
    _persist_llm_call: Callable[..., Any]
    _process_attempt: Callable[..., Any]
    _sem: Callable[..., Any]
    _set_failure_context: Callable[..., None]
    cfg: Any
    openrouter: Any

    def _schedule_background_task(
        self, coro: Coroutine[Any, Any, Any], label: str, correlation_id: str | None
    ) -> asyncio.Task[Any] | None:
        """Run a persistence task in the background and log errors."""
        try:
            task: asyncio.Task[Any] = asyncio.create_task(coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError as exc:
            logger.error(
                "background_task_schedule_failed",
                extra={"label": label, "cid": correlation_id, "error": str(exc)},
            )
            return None

        def _log_task_error(t: asyncio.Task[Any]) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "background_task_failed",
                    extra={"label": label, "cid": correlation_id, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

    async def aclose(self, timeout: float = 5.0) -> None:
        """Wait for all background tasks to complete."""
        if not self._background_tasks:
            return

        tasks = list(self._background_tasks)
        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(*tasks, return_exceptions=True)
        except TimeoutError:
            logger.warning(
                "llm_workflow_shutdown_timeout", extra={"pending": len(self._background_tasks)}
            )
        except Exception as e:
            raise_if_cancelled(e)
            logger.error("llm_workflow_shutdown_error", extra={"error": str(e)})

    async def execute_summary_workflow(
        self,
        *,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_config: Any,
        persistence: Any,
        repair_context: Any,
        requests: Sequence[Any],
        notifications: Any | None = None,
        ensure_summary: Callable[[dict[str, Any]], Any] | None = None,
        on_attempt: Callable[[Any], Any] | None = None,
        on_success: Callable[[dict[str, Any], Any], Any] | None = None,
        required_summary_fields: Sequence[str] = ("tldr", "summary_250", "summary_1000"),
        defer_persistence: bool = False,
    ) -> dict[str, Any] | None:
        """Run the shared summary processing workflow for a sequence of attempts."""
        if not requests:
            msg = "requests must include at least one attempt"
            raise ValueError(msg)

        from app.adapters.content.llm_response_workflow import AttemptContext

        failed_attempts: list[tuple[Any, Any]] = []
        total_attempts = len(requests)

        for attempt_index, attempt in enumerate(requests):
            is_last_attempt = attempt_index == total_attempts - 1

            on_retry = notifications.retry if notifications else None
            llm = await self._invoke_llm(attempt, req_id, on_retry=on_retry)

            if on_attempt is not None:
                await on_attempt(llm)

            if defer_persistence or persistence.defer_write:
                self._schedule_background_task(
                    self._persist_llm_call(llm, req_id, correlation_id),
                    "persist_llm_call",
                    correlation_id,
                )
            else:
                await self._persist_llm_call(llm, req_id, correlation_id)

            if (
                notifications
                and notifications.completion
                and (llm.status == "ok" or is_last_attempt)
            ):
                await notifications.completion(llm, attempt)

            summary = None
            try:
                attempt_ctx = AttemptContext(
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
                    required_summary_fields=tuple(required_summary_fields),
                    is_last_attempt=is_last_attempt,
                    failed_attempts=failed_attempts,
                    defer_persistence=defer_persistence,
                )
                summary = await self._process_attempt(attempt_ctx)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "summary_attempt_processing_failed",
                    extra={
                        "cid": correlation_id,
                        "preset": attempt.preset_name,
                        "model": attempt.model_override,
                        "error": str(exc),
                    },
                )
                self._set_failure_context(llm, "summary_processing_exception")
                context = getattr(llm, "error_context", None) or {}
                context.setdefault("message", "summary_processing_exception")
                context.setdefault("exception", str(exc))
                llm.error_context = context

            if summary is not None:
                return summary

            failed_attempts.append((llm, attempt))

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
        except (AttributeError, ValueError, RuntimeError):
            return {"type": "json_object"}

    async def persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        """Public helper to persist an LLM call."""
        await self._persist_llm_call(llm, req_id, correlation_id)

    async def _resolve_llm_timeout(self, model: str | None) -> tuple[float, str]:
        """Determine the LLM call timeout, preferring the adaptive service."""
        fixed_timeout = float(getattr(self.cfg.runtime, "llm_call_timeout_sec", 180.0))

        if self._adaptive_timeout is not None:
            try:
                adaptive_val = await self._adaptive_timeout.get_llm_timeout(model=model)
                if adaptive_val and adaptive_val > 0:
                    return float(adaptive_val), "adaptive"
            except Exception as exc:
                logger.warning(
                    "adaptive_timeout_lookup_failed",
                    extra={"model": model, "error": str(exc)},
                )

        return fixed_timeout, "fixed"

    async def _invoke_llm(self, request: Any, req_id: int, on_retry: Any | None = None) -> Any:
        from app.adapters.content.llm_response_workflow import ConcurrencyTimeoutError

        sem_timeout = getattr(self.cfg.runtime, "semaphore_acquire_timeout_sec", 30.0)
        llm_timeout, timeout_source = await self._resolve_llm_timeout(request.model_override)
        max_retries = getattr(self.cfg.runtime, "llm_call_max_retries", 2)

        logger.debug(
            "llm_timeout_resolved",
            extra={
                "req_id": req_id,
                "model": request.model_override,
                "llm_timeout_sec": llm_timeout,
                "timeout_source": timeout_source,
            },
        )

        for attempt in range(max_retries + 1):
            sem_cm = self._sem()
            try:
                async with asyncio.timeout(sem_timeout):
                    await sem_cm.__aenter__()
            except TimeoutError:
                logger.error(
                    "llm_semaphore_acquire_timeout",
                    extra={"req_id": req_id, "timeout_sec": sem_timeout, "attempt": attempt},
                )
                msg = f"Failed to acquire processing slot within {sem_timeout}s"
                raise ConcurrencyTimeoutError(msg) from None

            try:
                logger.debug(
                    "llm_semaphore_acquired",
                    extra={"req_id": req_id, "model": request.model_override},
                )
                async with asyncio.timeout(llm_timeout):
                    return await self.openrouter.chat(
                        request.messages,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        top_p=request.top_p,
                        stream=bool(getattr(request, "stream", False)),
                        request_id=req_id,
                        response_format=request.response_format,
                        model_override=request.model_override,
                        fallback_models_override=request.fallback_models_override,
                        on_stream_delta=getattr(request, "on_stream_delta", None),
                    )
            except TimeoutError:
                if attempt < max_retries:
                    logger.warning(
                        "llm_call_timeout_retrying",
                        extra={
                            "req_id": req_id,
                            "llm_timeout_sec": llm_timeout,
                            "timeout_source": timeout_source,
                            "model": request.model_override,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                        },
                    )
                    if on_retry:
                        try:
                            await on_retry()
                        except Exception as exc:
                            raise_if_cancelled(exc)
                            logger.exception("llm_on_retry_callback_failed")

                    await sleep_backoff(attempt, backoff_base=2.0, max_delay=30.0)
                    continue
                logger.error(
                    "llm_call_timeout",
                    extra={
                        "req_id": req_id,
                        "llm_timeout_sec": llm_timeout,
                        "timeout_source": timeout_source,
                        "model": request.model_override,
                        "attempts_exhausted": max_retries + 1,
                    },
                )
                raise
            finally:
                await sem_cm.__aexit__(None, None, None)

        msg = "LLM invoke loop exited unexpectedly"
        raise RuntimeError(msg)
