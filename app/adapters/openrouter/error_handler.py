"""Error handling and retry logic for OpenRouter API calls."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.models.llm.llm_models import LLMCallResult

if TYPE_CHECKING:
    from collections.abc import Callable


class ErrorHandler:
    """Handles errors, retries, and fallback logic for OpenRouter API calls."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
        auto_fallback_structured: bool = True,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._audit = audit
        self._auto_fallback_structured = auto_fallback_structured
        self._logger = logging.getLogger(__name__)

    async def sleep_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        import random

        base_delay = max(0.0, self._backoff_base * (2**attempt))
        jitter = 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(base_delay * jitter)

    def should_retry(self, status_code: int, attempt: int) -> bool:
        """Determine if a request should be retried based on status code and attempt."""
        if attempt >= self._max_retries:
            return False

        # Retryable errors (429, 5xx)
        return status_code == 429 or status_code >= 500

    def is_non_retryable_error(self, status_code: int) -> bool:
        """Check if error is non-retryable."""
        return status_code in (400, 401, 402, 403)

    def should_try_next_model(self, status_code: int) -> bool:
        """Determine if we should try the next model in fallback list."""
        return status_code == 404

    async def handle_rate_limit(self, response_headers: Any) -> None:
        """Handle rate limiting with proper delay."""
        retry_after = response_headers.get("retry-after")
        if retry_after:
            try:
                retry_seconds = int(retry_after)
                await asyncio.sleep(retry_seconds)
            except (ValueError, TypeError) as e:
                self._logger.warning(
                    "invalid_retry_after_header",
                    extra={"retry_after": retry_after, "error": str(e)},
                )

    def should_downgrade_response_format(
        self,
        status_code: int,
        data: dict,
        rf_mode_current: str,
        rf_included: bool,
        attempt: int,
    ) -> tuple[bool, str | None]:
        """Check if response format should be downgraded."""
        if not self._auto_fallback_structured:
            return False, None

        if status_code == 400 and rf_included:
            import json

            err_dump = json.dumps(data).lower()
            if "response_format" in err_dump:
                # Try downgrading from json_schema to json_object
                if rf_mode_current == "json_schema":
                    return True, "json_object"
                # If json_object also fails, disable structured outputs
                return True, None
        return False, None

    def build_error_result(
        self,
        model: str | None,
        text: str | None,
        data: dict | None,
        usage: dict,
        latency: int,
        error_message: str,
        headers: dict,
        messages: list[dict],
        *,
        error_context: dict | None = None,
    ) -> LLMCallResult:
        """Build error result consistently."""
        return LLMCallResult(
            status="error",
            model=model,
            response_text=text,
            response_json=data,
            openrouter_response_text=text,
            openrouter_response_json=data,
            tokens_prompt=usage.get("prompt_tokens"),
            tokens_completion=usage.get("completion_tokens"),
            cost_usd=None,
            latency_ms=latency,
            error_text=error_message,
            request_headers=headers,
            request_messages=messages,
            endpoint="/api/v1/chat/completions",
            structured_output_used=False,
            structured_output_mode=None,
            error_context=error_context,
        )

    def log_attempt(self, attempt: int, model: str, request_id: int | None = None) -> None:
        """Log attempt information."""
        if self._audit:
            self._audit(
                "INFO",
                "openrouter_attempt",
                {"attempt": attempt, "model": model, "request_id": request_id},
            )

    def log_success(
        self,
        attempt: int,
        model: str,
        status_code: int,
        latency: int,
        structured_output_used: bool,
        structured_output_mode: str | None,
        request_id: int | None = None,
    ) -> None:
        """Log successful request."""
        if self._audit:
            self._audit(
                "INFO",
                "openrouter_success",
                {
                    "attempt": attempt,
                    "model": model,
                    "status": status_code,
                    "latency_ms": latency,
                    "structured_output": structured_output_used,
                    "rf_mode": structured_output_mode,
                    "request_id": request_id,
                },
            )

    def log_error(
        self,
        attempt: int,
        model: str,
        status_code: int,
        error_message: str,
        request_id: int | None = None,
        severity: str = "ERROR",
    ) -> None:
        """Log error information."""
        if self._audit:
            self._audit(
                severity,
                "openrouter_error",
                {
                    "attempt": attempt,
                    "model": model,
                    "status": status_code,
                    "error": error_message,
                    "request_id": request_id,
                },
            )

    def log_fallback(
        self,
        from_model: str,
        to_model: str,
        request_id: int | None = None,
    ) -> None:
        """Log model fallback."""
        if self._audit:
            self._audit(
                "WARN",
                "openrouter_fallback",
                {
                    "from_model": from_model,
                    "to_model": to_model,
                    "request_id": request_id,
                },
            )

    def log_exhausted(
        self,
        models_tried: list[str],
        attempts_each: int,
        error: str | None,
        request_id: int | None = None,
    ) -> None:
        """Log when all models and retries are exhausted."""
        if self._audit:
            self._audit(
                "ERROR",
                "openrouter_exhausted",
                {
                    "models_tried": models_tried,
                    "attempts_each": attempts_each,
                    "error": error,
                    "request_id": request_id,
                },
            )

    def log_skip_model(self, model: str, reason: str, request_id: int | None = None) -> None:
        """Log when a model is skipped."""
        if self._audit:
            self._audit(
                "WARN",
                f"openrouter_skip_model_{reason}",
                {"model": model, "request_id": request_id},
            )

    def log_response_format_downgrade(
        self, model: str, from_mode: str, to_mode: str, request_id: int | None = None
    ) -> None:
        """Log response format downgrade."""
        if self._audit:
            self._audit(
                "WARN",
                "openrouter_downgrade_json_schema_to_object",
                {"model": model, "request_id": request_id},
            )

        self._logger.warning(
            "downgrade_response_format",
            extra={
                "model": model,
                "from": from_mode,
                "to": to_mode,
            },
        )

    def log_structured_outputs_disabled(self, model: str, request_id: int | None = None) -> None:
        """Log when structured outputs are disabled."""
        if self._audit:
            self._audit(
                "WARN",
                "openrouter_disable_structured_outputs",
                {"model": model, "request_id": request_id},
            )

        self._logger.warning("disable_structured_outputs", extra={"model": model})

    def log_truncated_completion(
        self,
        model: str,
        finish_reason: str | None,
        native_finish_reason: str | None,
        request_id: int | None = None,
    ) -> None:
        """Log when a completion stops because of output length limits."""
        if self._audit:
            self._audit(
                "WARN",
                "openrouter_truncated_completion",
                {
                    "model": model,
                    "finish_reason": finish_reason,
                    "native_finish_reason": native_finish_reason,
                    "request_id": request_id,
                },
            )

        self._logger.warning(
            "completion_truncated",
            extra={
                "model": model,
                "finish_reason": finish_reason,
                "native_finish_reason": native_finish_reason,
            },
        )
