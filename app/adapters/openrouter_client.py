from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging_utils import truncate_log_content


@dataclass
class LLMCallResult:
    status: str
    model: str | None
    response_text: str | None
    response_json: dict | None
    tokens_prompt: int | None
    tokens_completion: int | None
    cost_usd: float | None
    latency_ms: int | None
    error_text: str | None
    request_headers: dict | None = None
    request_messages: list[dict] | None = None
    endpoint: str | None = "/api/v1/chat/completions"


class OpenRouterClient:
    """Minimal OpenRouter Chat Completions client (async)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        fallback_models: list[str] | tuple[str, ...] | None = None,
        http_referer: str | None = None,
        x_title: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
        debug_payloads: bool = False,
        provider_order: list[str] | tuple[str, ...] | None = None,
        enable_stats: bool = False,
        log_truncate_length: int = 1000,
    ) -> None:
        # Security: Validate API key presence. Length/format is enforced at config load.
        if not api_key or not isinstance(api_key, str):
            raise ValueError("API key is required")

        # Security: Validate model
        if not model or not isinstance(model, str):
            raise ValueError("Model is required")
        if len(model) > 100:
            raise ValueError("Model name too long")

        # Security: Validate fallback models
        validated_fallbacks = []
        if fallback_models:
            for fallback in fallback_models:
                if isinstance(fallback, str) and fallback and len(fallback) <= 100:
                    validated_fallbacks.append(fallback)

        # Security: Validate headers
        if http_referer and (not isinstance(http_referer, str) or len(http_referer) > 500):
            raise ValueError("HTTP referer too long")
        if x_title and (not isinstance(x_title, str) or len(x_title) > 200):
            raise ValueError("X-Title too long")

        # Security: Validate timeout
        if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
            raise ValueError("Timeout must be positive")
        if timeout_sec > 300:  # 5 minutes max
            raise ValueError("Timeout too large")

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        # Allow zero to disable waits in tests; only negative is invalid
        if not isinstance(backoff_base, int | float) or backoff_base < 0:
            raise ValueError("Backoff base must be non-negative")

        self._api_key = api_key
        self._model = model
        self._fallback_models = validated_fallbacks
        self._timeout = int(timeout_sec)
        self._base_url = "https://openrouter.ai/api/v1"
        self._http_referer = http_referer
        self._x_title = x_title
        self._max_retries = max(0, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._audit = audit
        self._logger = logging.getLogger(__name__)
        self._debug_payloads = bool(debug_payloads)
        self._provider_order = list(provider_order or [])
        self._enable_stats = bool(enable_stats)
        self._log_truncate_length = int(log_truncate_length)

    def _get_error_message(self, status_code: int, data: dict) -> str:
        """Get descriptive error message based on HTTP status code."""
        error_messages = {
            400: "Invalid or missing request parameters",
            401: "Authentication failed (invalid or expired API key)",
            402: "Insufficient account balance",
            404: "Requested resource not found",
            429: "Rate limit exceeded",
            500: "Internal server error",
        }

        base_message = error_messages.get(status_code, f"HTTP {status_code} error")
        api_error = (
            data.get("error", {}).get("message")
            if isinstance(data.get("error"), dict)
            else data.get("error")
        )

        if api_error:
            return f"{base_message}: {api_error}"
        return base_message

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
        request_id: int | None = None,
    ) -> LLMCallResult:
        # Security: Validate messages
        if not messages or not isinstance(messages, list):
            raise ValueError("Messages list is required")
        if len(messages) > 50:  # Prevent extremely long conversations
            raise ValueError("Too many messages")

        # Security: Validate message structure
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"Message {i} must be a dictionary")
            if "role" not in msg or "content" not in msg:
                raise ValueError(f"Message {i} missing required fields")
            if not isinstance(msg["role"], str) or msg["role"] not in {
                "system",
                "user",
                "assistant",
            }:
                raise ValueError(f"Message {i} has invalid role")
            if not isinstance(msg["content"], str):
                raise ValueError(f"Message {i} content must be string")
            if len(msg["content"]) > 50000:  # Prevent extremely long messages
                # Truncate rather than erroring out; preserve ending marker
                msg["content"] = (
                    msg["content"][: self._log_truncate_length] + "... [input truncated]"
                )

        # Security: Validate temperature
        if not isinstance(temperature, int | float):
            raise ValueError("Temperature must be numeric")
        if temperature < 0 or temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")

        # Security: Validate max_tokens
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ValueError("Max tokens must be a positive integer")
            if max_tokens > 100000:  # Reasonable upper limit
                raise ValueError("Max tokens too large")

        # Security: Validate top_p
        if top_p is not None:
            if not isinstance(top_p, int | float):
                raise ValueError("Top_p must be numeric")
            if top_p < 0 or top_p > 1:
                raise ValueError("Top_p must be between 0 and 1")

        # Security: Validate stream
        if not isinstance(stream, bool):
            raise ValueError("Stream must be boolean")

        # Security: Validate request_id
        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            raise ValueError("Invalid request_id")
        models_to_try = [self._model] + self._fallback_models
        last_error_text = None
        last_data = None
        last_latency = None
        last_model_reported = None

        for model in models_to_try:
            for attempt in range(self._max_retries + 1):
                if self._audit:
                    self._audit(
                        "INFO",
                        "openrouter_attempt",
                        {"attempt": attempt, "model": model, "request_id": request_id},
                    )
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
                    "X-Title": self._x_title or "Bite-Size Reader Bot",
                }

                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }

                # Add optional parameters
                if max_tokens is not None:
                    body["max_tokens"] = max_tokens
                if top_p is not None:
                    body["top_p"] = top_p
                if stream:
                    body["stream"] = stream
                # Provider routing best-practice: allow order preference
                if self._provider_order:
                    body["route"] = {"order": list(self._provider_order)}

                started = time.perf_counter()
                try:
                    self._logger.debug(
                        "openrouter_request",
                        extra={"model": model, "attempt": attempt, "messages_len": len(messages)},
                    )
                    if self._debug_payloads:
                        red_header = dict(headers)
                        if "Authorization" in red_header:
                            red_header["Authorization"] = "REDACTED"
                        self._logger.debug(
                            "openrouter_request_payload",
                            extra={
                                "headers": red_header,
                                "body_preview": {
                                    "model": model,
                                    "messages": messages[:3],
                                    "temperature": temperature,
                                },
                            },
                        )
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        resp = await client.post(
                            f"{self._base_url}/chat/completions", headers=headers, json=body
                        )
                    latency = int((time.perf_counter() - started) * 1000)
                    data = resp.json()
                    last_latency = latency
                    last_data = data
                    last_model_reported = data.get("model", model)
                    self._logger.debug(
                        "openrouter_response",
                        extra={
                            "status": resp.status_code,
                            "latency_ms": latency,
                            "model": last_model_reported,
                        },
                    )
                    if self._debug_payloads:
                        # Avoid dumping huge payloads entirely
                        try:
                            preview = data
                            # Truncate large response content
                            if isinstance(preview, dict) and "choices" in preview:
                                choices = preview.get("choices", [])
                                if choices and isinstance(choices[0], dict):
                                    choice = choices[0]
                                    if "message" in choice and isinstance(choice["message"], dict):
                                        content = choice["message"].get("content")
                                        if content:
                                            choice["message"]["content"] = truncate_log_content(
                                                content, self._log_truncate_length
                                            )
                            self._logger.debug(
                                "openrouter_response_payload", extra={"preview": preview}
                            )
                        except Exception:
                            pass

                    status_code = resp.status_code
                    # Extract text and usage
                    text = None
                    try:
                        choices = data.get("choices") or []
                        if choices:
                            text = choices[0].get("message", {}).get("content")
                    except Exception:
                        text = None

                    usage = data.get("usage") or {}
                    # Optional stats (provider/native tokens/cost) if present
                    cost_usd = None
                    if self._enable_stats:
                        try:
                            cost_usd = float(data.get("usage", {}).get("total_cost", 0.0))
                        except Exception:
                            cost_usd = None
                    # redact Authorization
                    redacted_headers = dict(headers)
                    if "Authorization" in redacted_headers:
                        redacted_headers["Authorization"] = "REDACTED"

                    # Handle different HTTP status codes according to OpenRouter documentation
                    if status_code == 200:
                        if self._audit:
                            self._audit(
                                "INFO",
                                "openrouter_success",
                                {
                                    "attempt": attempt,
                                    "model": model,
                                    "status": status_code,
                                    "latency_ms": latency,
                                    "request_id": request_id,
                                },
                            )
                        return LLMCallResult(
                            status="ok",
                            model=last_model_reported,
                            response_text=text,
                            response_json=data,
                            tokens_prompt=usage.get("prompt_tokens"),
                            tokens_completion=usage.get("completion_tokens"),
                            cost_usd=cost_usd,
                            latency_ms=latency,
                            error_text=None,
                            request_headers=redacted_headers,
                            request_messages=messages,
                            endpoint="/api/v1/chat/completions",
                        )

                    # Handle specific HTTP status codes according to OpenRouter documentation
                    error_message = self._get_error_message(status_code, data)

                    # Non-retryable errors (400, 401, 402, 404)
                    if status_code in (400, 401, 402, 404):
                        if self._audit:
                            self._audit(
                                "ERROR",
                                "openrouter_error",
                                {
                                    "attempt": attempt,
                                    "model": model,
                                    "status": status_code,
                                    "error": error_message,
                                    "request_id": request_id,
                                },
                            )
                        return LLMCallResult(
                            status="error",
                            model=last_model_reported,
                            response_text=text,
                            response_json=data,
                            tokens_prompt=usage.get("prompt_tokens"),
                            tokens_completion=usage.get("completion_tokens"),
                            cost_usd=None,
                            latency_ms=latency,
                            error_text=error_message,
                            request_headers=redacted_headers,
                            request_messages=messages,
                            endpoint="/api/v1/chat/completions",
                        )

                    # Retryable errors (429, 5xx)
                    if status_code == 429 or status_code >= 500:
                        last_error_text = error_message
                        if attempt < self._max_retries:
                            # For 429, respect retry_after header if present
                            if status_code == 429:
                                retry_after = resp.headers.get("retry-after")
                                if retry_after:
                                    try:
                                        retry_seconds = int(retry_after)
                                        await asyncio.sleep(retry_seconds)
                                        continue
                                    except (ValueError, TypeError):
                                        pass
                            await asyncio_sleep_backoff(self._backoff_base, attempt)
                            continue
                        else:
                            break  # move to next model
                    else:
                        # Unknown status code, treat as non-retryable error
                        if self._audit:
                            self._audit(
                                "ERROR",
                                "openrouter_error",
                                {
                                    "attempt": attempt,
                                    "model": model,
                                    "status": status_code,
                                    "error": error_message,
                                    "request_id": request_id,
                                },
                            )
                        return LLMCallResult(
                            status="error",
                            model=last_model_reported,
                            response_text=text,
                            response_json=data,
                            tokens_prompt=usage.get("prompt_tokens"),
                            tokens_completion=usage.get("completion_tokens"),
                            cost_usd=None,
                            latency_ms=latency,
                            error_text=error_message,
                            request_headers=redacted_headers,
                            request_messages=messages,
                            endpoint="/api/v1/chat/completions",
                        )
                except Exception as e:  # noqa: BLE001
                    latency = int((time.perf_counter() - started) * 1000)
                    last_latency = latency
                    last_error_text = str(e)
                    self._logger.error(
                        "openrouter_exception", extra={"error": str(e), "attempt": attempt}
                    )
                    if attempt < self._max_retries:
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                    else:
                        break  # next model

            # moving to fallback model
            if self._audit and model != models_to_try[-1]:
                self._audit(
                    "WARN",
                    "openrouter_fallback",
                    {
                        "from_model": model,
                        "to_model": models_to_try[models_to_try.index(model) + 1],
                        "request_id": request_id,
                    },
                )

        # All models exhausted
        redacted_headers = {
            "Authorization": "REDACTED",
            "Content-Type": "application/json",
        }
        if self._audit:
            self._audit(
                "ERROR",
                "openrouter_exhausted",
                {
                    "models_tried": models_to_try,
                    "attempts_each": self._max_retries + 1,
                    "error": last_error_text,
                    "request_id": request_id,
                },
            )
        return LLMCallResult(
            status="error",
            model=last_model_reported,
            response_text=None,
            response_json=last_data,
            tokens_prompt=None,
            tokens_completion=None,
            cost_usd=None,
            latency_ms=last_latency,
            error_text=last_error_text or "All retries and fallbacks exhausted",
            request_headers=redacted_headers,
            request_messages=messages,
            endpoint="/v1/chat/completions",
        )

    async def get_models(self) -> dict:
        """Get available models from OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self._logger.error("openrouter_models_error", extra={"error": str(e)})
            raise


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    # Exponential backoff with light jitter: (base * 2^attempt) * (1 +/- 0.25)
    import asyncio
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
