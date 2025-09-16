from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.json_utils import extract_json
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
        if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0:  # noqa: UP038
            raise ValueError("Timeout must be positive")
        if timeout_sec > 300:  # 5 minutes max
            raise ValueError("Timeout too large")

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        # Allow zero to disable waits in tests; only negative is invalid
        if not isinstance(backoff_base, (int, float)) or backoff_base < 0:  # noqa: UP038
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
        self._rf_supported = True
        # Cache capabilities: which models support structured outputs
        self._structured_supported_models: set[str] | None = None
        self._capabilities_last_load: float = 0.0
        self._capabilities_ttl_sec: int = 3600

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

    def _sanitize_user_content(self, text: str) -> str:
        patterns = [
            r"(?i)ignore previous instructions",
            r"(?i)forget previous instructions",
            r"(?i)system:",
            r"(?i)assistant:",
            r"(?i)user:",
            r"```",
        ]
        sanitized = text
        for pat in patterns:
            sanitized = re.sub(pat, "", sanitized)
        return sanitized

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
        request_id: int | None = None,
        response_format: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> LLMCallResult:
        # Security: Validate messages
        if not messages or not isinstance(messages, list):
            raise ValueError("Messages list is required")
        if len(messages) > 50:  # Prevent extremely long conversations
            raise ValueError("Too many messages")

        sanitized_messages = []
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
                # Do not truncate the actual content sent to the provider.
                # We only truncate in debug logs below to avoid log bloat.
                # Let the provider handle context window limits.
                pass
            if msg["role"] == "user":
                sanitized_content = self._sanitize_user_content(msg["content"])
                if sanitized_content != msg["content"]:
                    msg = {**msg, "content": sanitized_content}
            sanitized_messages.append(msg)
        messages = sanitized_messages

        # Security: Validate temperature
        if not isinstance(temperature, (int, float)):  # noqa: UP038
            # noqa: UP038
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
            if not isinstance(top_p, (int, float)):  # noqa: UP038
                # noqa: UP038
                raise ValueError("Top_p must be numeric")
            if top_p < 0 or top_p > 1:
                raise ValueError("Top_p must be between 0 and 1")

        # Security: Validate stream
        if not isinstance(stream, bool):
            raise ValueError("Stream must be boolean")

        # Security: Validate request_id
        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            raise ValueError("Invalid request_id")
        primary_model = model_override if model_override else self._model
        models_to_try = [primary_model] + self._fallback_models

        # If caller expects structured outputs via response_format and the primary model
        # is reasoning-heavy, append safe structured-output models as implicit fallbacks
        def _is_reasoning_heavy(name: str) -> bool:
            n = name.lower()
            # Treat GPT-5 family as reasoning-heavy; restrict to supported set
            return "gpt-5" in n

        def _append_if_missing(seq: list[str], items: list[str]) -> None:
            seen = {m for m in seq}
            for it in items:
                if it not in seen:
                    seq.append(it)
                    seen.add(it)

        safe_structured_models = [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
        ]

        # Only add implicit fallbacks if structured outputs requested
        if response_format is not None and _is_reasoning_heavy(primary_model):
            _append_if_missing(models_to_try, safe_structured_models)
        last_error_text = None
        last_data = None
        last_latency = None
        last_model_reported = None
        last_response_text = None

        for model in models_to_try:
            # Track response_format mode per model: may downgrade json_schema -> json_object
            requested_rf = response_format if isinstance(response_format, dict) else None
            rf_mode_current: str | None = None
            if requested_rf:
                rf_mode_current = str(requested_rf.get("type") or "json_object")
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

                # Include response_format whenever requested. This ensures that if the caller
                # expects structured output, a plain-text response will be treated as an error
                # (structured_output_parse_error) and we will not silently fall back to other models.
                rf_included = False
                want_rf = bool(requested_rf)
                if want_rf:
                    if requested_rf and isinstance(requested_rf, dict):
                        # Possibly downgraded mode
                        if rf_mode_current == "json_schema":
                            body["response_format"] = requested_rf
                        elif rf_mode_current == "json_object":
                            body["response_format"] = {"type": "json_object"}
                        else:
                            body["response_format"] = requested_rf
                    else:
                        body["response_format"] = {"type": "json_object"}
                    rf_included = True
                    # Provider hint: best-effort; safe if ignored by backend
                    try:
                        body["provider"] = {"require_parameters": True}
                    except Exception:
                        pass

                # Intelligent compression strategy based on OpenRouter best practices
                # Apply middle-out compression only when content significantly exceeds context limits
                total_content_length = sum(len(msg.get("content", "")) for msg in messages)

                # Adaptive compression thresholds based on supported models
                model_lower = model.lower()
                if "gpt-5" in model_lower:
                    compression_threshold = 800000  # ~0.8MB for very large context
                elif "gpt-4o" in model_lower:
                    compression_threshold = 350000  # ~350KB for 128k
                elif "gemini-2.5" in model_lower:
                    compression_threshold = 1200000  # ~1.2MB for 1M tokens
                else:
                    compression_threshold = 200000  # conservative fallback

                if total_content_length > compression_threshold:
                    body["transforms"] = ["middle-out"]
                    self._logger.warning(
                        "middle_out_compression_applied",
                        extra={
                            "total_content_length": total_content_length,
                            "threshold": compression_threshold,
                            "reason": "content_exceeds_safe_context_limit",
                        },
                    )
                else:
                    # Log when we're approaching the threshold (75% or more) for monitoring
                    warning_threshold = int(
                        compression_threshold * 0.75
                    )  # 75% of compression threshold
                    if total_content_length > warning_threshold:
                        self._logger.info(
                            "large_content_detected",
                            extra={
                                "total_content_length": total_content_length,
                                "compression_threshold": compression_threshold,
                                "warning_threshold": warning_threshold,
                                "model": model,
                                "compression_applied": False,
                                "percentage_of_threshold": round(
                                    (total_content_length / compression_threshold) * 100, 1
                                ),
                            },
                        )

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
                        preview_rf = body.get("response_format") or {}
                        rf_type = preview_rf.get("type") if isinstance(preview_rf, dict) else None
                        # Calculate content lengths for verification
                        content_lengths = [len(msg.get("content", "")) for msg in messages]
                        total_content = sum(content_lengths)

                        # Show truncated messages for debug but include content length info
                        debug_messages = []
                        for i, msg in enumerate(messages[:3]):
                            debug_msg = dict(msg)
                            content = debug_msg.get("content", "")
                            if len(content) > 200:  # Truncate for logging only
                                debug_msg["content"] = (
                                    content[:100] + f"... [+{len(content) - 100} chars]"
                                )
                            debug_msg["content_length"] = str(len(content))
                            debug_messages.append(debug_msg)

                        self._logger.debug(
                            "openrouter_request_payload",
                            extra={
                                "headers": red_header,
                                "body_preview": {
                                    "model": model,
                                    "messages": debug_messages,
                                    "temperature": temperature,
                                    "response_format_type": rf_type,
                                    "total_content_length": total_content,
                                    "content_lengths": content_lengths,
                                    "transforms": body.get("transforms"),
                                },
                            },
                        )
                    # Use connection pooling to reduce TCP handshake overhead
                    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
                    async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
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
                                        msg_content: Any = choice["message"].get("content")
                                        if msg_content and isinstance(msg_content, str):
                                            truncated_content = truncate_log_content(
                                                msg_content, self._log_truncate_length
                                            )
                                            choice["message"]["content"] = truncated_content
                            self._logger.debug(
                                "openrouter_response_payload", extra={"preview": preview}
                            )
                        except Exception:
                            pass

                    status_code = resp.status_code
                    if status_code == 400 and rf_included:
                        err_dump = json.dumps(data).lower()
                        if "response_format" in err_dump:
                            # If json_schema appears unsupported, gracefully downgrade to json_object
                            prev_mode = rf_mode_current or (requested_rf or {}).get("type")
                            if (prev_mode or "").lower() == "json_schema":
                                rf_mode_current = "json_object"
                                if self._audit:
                                    self._audit(
                                        "WARN",
                                        "openrouter_downgrade_json_schema_to_object",
                                        {"model": model, "request_id": request_id},
                                    )
                                self._logger.warning(
                                    "downgrade_response_format", extra={"model": model}
                                )
                                if attempt < self._max_retries:
                                    # Retry same model with json_object
                                    await asyncio_sleep_backoff(self._backoff_base, attempt)
                                    continue
                            # If even json_object seems unsupported, disable RF for subsequent attempts
                            self._rf_supported = False
                            if self._audit:
                                self._audit(
                                    "WARN",
                                    "openrouter_response_format_unsupported",
                                    {"model": model, "request_id": request_id},
                                )
                            self._logger.warning(
                                "openrouter_response_format_unsupported", extra={"model": model}
                            )
                            if attempt < self._max_retries:
                                await asyncio_sleep_backoff(self._backoff_base, attempt)
                                continue
                    # Extract text and usage
                    text = None
                    try:
                        choices = data.get("choices") or []
                        if choices:
                            message_obj = choices[0].get("message", {}) or {}
                            # Prefer parsed when structured outputs were included
                            prefer_parsed = rf_included

                            if prefer_parsed:
                                parsed = message_obj.get("parsed")
                                if parsed is not None:
                                    try:
                                        text = json.dumps(parsed, ensure_ascii=False)
                                    except Exception:
                                        text = str(parsed)

                            if (not text) or (isinstance(text, str) and not text.strip()):
                                content_field = message_obj.get("content")
                                # Primary: plain string content
                                if isinstance(content_field, str):
                                    text = content_field
                                # Some providers return content as array of parts
                                elif isinstance(content_field, list):
                                    try:
                                        parts: list[str] = []
                                        for part in content_field:
                                            if isinstance(part, dict):
                                                if isinstance(part.get("text"), str):
                                                    parts.append(part["text"])
                                                elif isinstance(part.get("content"), str):
                                                    parts.append(part["content"])
                                        if parts:
                                            text = "\n".join(parts)
                                    except Exception:
                                        pass

                            # If still nothing meaningful, try reasoning field to recover JSON
                            if (not text) or (isinstance(text, str) and not text.strip()):
                                reasoning = message_obj.get("reasoning")
                                if reasoning and isinstance(reasoning, str):
                                    # Look for JSON in reasoning field
                                    start = reasoning.find("{")
                                    end = reasoning.rfind("}")
                                    if start != -1 and end != -1 and end > start:
                                        try:
                                            potential_json = reasoning[start : end + 1]
                                            # Validate it's valid JSON
                                            json.loads(potential_json)
                                            text = potential_json
                                        except Exception:
                                            text = reasoning

                            # Function/tool calls: arguments may hold the JSON
                            if (not text) or (isinstance(text, str) and not text.strip()):
                                tool_calls = message_obj.get("tool_calls") or []
                                if tool_calls and isinstance(tool_calls, list):
                                    try:
                                        first = tool_calls[0] or {}
                                        fn = (
                                            (first.get("function") or {})
                                            if isinstance(first, dict)
                                            else {}
                                        )
                                        args = fn.get("arguments")
                                        if isinstance(args, str):
                                            text = args
                                        elif isinstance(args, dict):
                                            text = json.dumps(args, ensure_ascii=False)
                                    except Exception:
                                        pass
                    except Exception:
                        text = None

                    if isinstance(text, str):
                        last_response_text = text

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
                        # If structured outputs were included, ensure we actually got JSON
                        if rf_included:
                            text_str = text or ""
                            parsed = extract_json(text_str)
                            if parsed is not None:
                                try:
                                    text = json.dumps(parsed, ensure_ascii=False)
                                    last_response_text = text
                                except Exception:
                                    last_response_text = text_str
                            else:
                                last_error_text = "structured_output_parse_error"
                                last_data = data
                                last_latency = latency
                                last_response_text = text_str or None
                                if self._audit:
                                    self._audit(
                                        "WARN",
                                        "openrouter_invalid_json_content",
                                        {
                                            "attempt": attempt,
                                            "model": model,
                                            "status": status_code,
                                            "request_id": request_id,
                                        },
                                    )
                                break
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

            if last_error_text == "structured_output_parse_error":
                break

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
            response_text=last_response_text,
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

    async def _ensure_structured_supported_models(self) -> None:
        """Fetch and cache the set of models supporting structured outputs.

        Uses OpenRouter's models endpoint with supported_parameters=structured_outputs.
        Caches results for a TTL to avoid repeated network calls.
        """
        now = time.time()
        if (
            self._structured_supported_models is not None
            and (now - self._capabilities_last_load) < self._capabilities_ttl_sec
        ):
            return
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }
        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
                resp = await client.get(
                    f"{self._base_url}/models?supported_parameters=structured_outputs",
                    headers=headers,
                )
                resp.raise_for_status()
                payload = resp.json()
                arr = []
                if isinstance(payload, dict):
                    if isinstance(payload.get("data"), list):
                        arr = payload.get("data")
                    elif isinstance(payload.get("models"), list):
                        arr = payload.get("models")
                models: set[str] = set()
                for it in arr or []:
                    try:
                        if isinstance(it, dict):
                            mid = it.get("id") or it.get("name") or it.get("model") or None
                            if isinstance(mid, str) and mid:
                                models.add(mid)
                    except Exception:
                        continue
                if models:
                    self._structured_supported_models = models
                else:
                    # Keep None to indicate unknown; don't overwrite with empty set
                    self._structured_supported_models = self._structured_supported_models
                self._capabilities_last_load = now
        except Exception as e:  # noqa: BLE001
            # Don't fail the request; just log and continue without capabilities
            self._capabilities_last_load = now
            self._logger.warning("openrouter_capabilities_probe_failed", extra={"error": str(e)})

    async def get_models(self) -> dict:
        """Get available models from OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }

        try:
            # Use connection pooling to reduce TCP handshake overhead
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
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
