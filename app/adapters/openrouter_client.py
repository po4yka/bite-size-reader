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
    structured_output_used: bool = False
    structured_output_mode: str | None = None


class OpenRouterClient:
    """Enhanced OpenRouter Chat Completions client with structured output support."""

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
        # Structured output settings
        enable_structured_outputs: bool = True,
        structured_output_mode: str = "json_schema",
        require_parameters: bool = True,
        auto_fallback_structured: bool = True,
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
        if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0:
            raise ValueError("Timeout must be positive")
        if timeout_sec > 300:  # 5 minutes max
            raise ValueError("Timeout too large")

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        if not isinstance(backoff_base, (int, float)) or backoff_base < 0:
            raise ValueError("Backoff base must be non-negative")

        # Validate structured output settings
        if structured_output_mode not in {"json_schema", "json_object"}:
            raise ValueError("Structured output mode must be 'json_schema' or 'json_object'")

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

        # Structured output settings
        self._enable_structured_outputs = bool(enable_structured_outputs)
        self._structured_output_mode = structured_output_mode
        self._require_parameters = bool(require_parameters)
        self._auto_fallback_structured = bool(auto_fallback_structured)

        # Cache capabilities: which models support structured outputs
        self._structured_supported_models: set[str] | None = None
        self._capabilities_last_load: float = 0.0
        self._capabilities_ttl_sec: int = 3600

        # Known models that support structured outputs (fallback list)
        self._known_structured_models = {
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4o-2024-08-06",
            "openai/gpt-4o-2024-11-20",
            "openai/gpt-5",
            "openai/gpt-5-mini",
            "openai/gpt-5-nano",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "anthropic/claude-3-5-sonnet",
            "anthropic/claude-3-5-haiku",
        }

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
        """Sanitize user content to prevent prompt injection."""
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

    def _is_reasoning_heavy_model(self, model: str) -> bool:
        """Check if model is reasoning-heavy (like GPT-5 family)."""
        model_lower = model.lower()
        reasoning_indicators = ["gpt-5", "o1", "reasoning"]
        return any(indicator in model_lower for indicator in reasoning_indicators)

    def _get_safe_structured_fallbacks(self) -> list[str]:
        """Get list of models known to support structured outputs reliably."""
        return [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
        ]

    def _supports_structured_outputs(self, model: str) -> bool:
        """Check if a model supports structured outputs."""
        # Check cached capabilities first
        if self._structured_supported_models:
            return model in self._structured_supported_models

        # Fallback to known models list
        return model in self._known_structured_models

    def _build_response_format(self, response_format: dict[str, Any] | None, mode: str) -> dict[str, Any] | None:
        """Build response format based on mode and input."""
        if not response_format or not self._enable_structured_outputs:
            return None

        if mode == "json_schema" and "schema" in response_format:
            return {
                "type": "json_schema",
                "json_schema": response_format
            }
        elif mode == "json_object" or "schema" not in response_format:
            return {"type": "json_object"}
        else:
            return response_format

    def _extract_structured_content(self, message_obj: dict, rf_included: bool) -> str | None:
        """Extract structured content from response message."""
        text = None

        # Prefer parsed field when structured outputs were requested
        if rf_included:
            parsed = message_obj.get("parsed")
            if parsed is not None:
                try:
                    text = json.dumps(parsed, ensure_ascii=False)
                except Exception:
                    text = str(parsed)

        # Fallback to content field
        if not text or (isinstance(text, str) and not text.strip()):
            content_field = message_obj.get("content")

            if isinstance(content_field, str):
                text = content_field
            elif isinstance(content_field, list):
                # Handle content as array of parts
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

        # Try reasoning field for o1-style models
        if not text or (isinstance(text, str) and not text.strip()):
            reasoning = message_obj.get("reasoning")
            if reasoning and isinstance(reasoning, str):
                # Look for JSON in reasoning field
                start = reasoning.find("{")
                end = reasoning.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        potential_json = reasoning[start : end + 1]
                        json.loads(potential_json)  # Validate JSON
                        text = potential_json
                    except Exception:
                        text = reasoning

        # Try function/tool calls
        if not text or (isinstance(text, str) and not text.strip()):
            tool_calls = message_obj.get("tool_calls") or []
            if tool_calls and isinstance(tool_calls, list):
                try:
                    first = tool_calls[0] or {}
                    fn = (first.get("function") or {}) if isinstance(first, dict) else {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        text = args
                    elif isinstance(args, dict):
                        text = json.dumps(args, ensure_ascii=False)
                except Exception:
                    pass

        return text

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
        """Enhanced chat method with structured output support."""

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

            # Sanitize user content
            if msg["role"] == "user":
                sanitized_content = self._sanitize_user_content(msg["content"])
                if sanitized_content != msg["content"]:
                    msg = {**msg, "content": sanitized_content}
            sanitized_messages.append(msg)
        messages = sanitized_messages

        # Validate other parameters
        if not isinstance(temperature, (int, float)):
            raise ValueError("Temperature must be numeric")
        if temperature < 0 or temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")

        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ValueError("Max tokens must be a positive integer")
            if max_tokens > 100000:
                raise ValueError("Max tokens too large")

        if top_p is not None:
            if not isinstance(top_p, (int, float)):
                raise ValueError("Top_p must be numeric")
            if top_p < 0 or top_p > 1:
                raise ValueError("Top_p must be between 0 and 1")

        if not isinstance(stream, bool):
            raise ValueError("Stream must be boolean")

        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            raise ValueError("Invalid request_id")

        # Determine models to try
        primary_model = model_override if model_override else self._model
        models_to_try = [primary_model] + self._fallback_models

        # Add structured output fallbacks if needed
        if (response_format is not None and
            self._enable_structured_outputs and
            self._is_reasoning_heavy_model(primary_model)):

            safe_models = self._get_safe_structured_fallbacks()
            for safe_model in safe_models:
                if safe_model not in models_to_try:
                    models_to_try.append(safe_model)

        # Track state across attempts
        last_error_text = None
        last_data = None
        last_latency = None
        last_model_reported = None
        last_response_text = None
        structured_output_used = False
        structured_output_mode_used = None

        # Try each model
        for model in models_to_try:
            # Determine response format mode for this model
            rf_mode_current = self._structured_output_mode
            requested_rf = response_format if isinstance(response_format, dict) else None

            # Skip models that don't support structured outputs if required
            if requested_rf and self._enable_structured_outputs:
                await self._ensure_structured_supported_models()
                if not self._supports_structured_outputs(model):
                    if self._audit:
                        self._audit(
                            "WARN",
                            "openrouter_skip_model_no_structured_outputs",
                            {"model": model, "request_id": request_id},
                        )
                    continue

            # Retry logic for each model
            for attempt in range(self._max_retries + 1):
                if self._audit:
                    self._audit(
                        "INFO",
                        "openrouter_attempt",
                        {"attempt": attempt, "model": model, "request_id": request_id},
                    )

                # Build headers
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
                    "X-Title": self._x_title or "Bite-Size Reader Bot",
                }

                # Build request body
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

                # Provider routing configuration
                provider_prefs: dict[str, Any] = {}
                if self._provider_order:
                    provider_prefs["order"] = list(self._provider_order)

                # Add response format if structured outputs enabled
                rf_included = False
                if requested_rf and self._enable_structured_outputs:
                    built_rf = self._build_response_format(requested_rf, rf_mode_current)
                    if built_rf:
                        body["response_format"] = built_rf
                        rf_included = True
                        structured_output_used = True
                        structured_output_mode_used = rf_mode_current

                        if self._require_parameters:
                            provider_prefs["require_parameters"] = True

                # Attach provider preferences
                if provider_prefs:
                    body["provider"] = provider_prefs

                # Apply content compression if needed
                total_content_length = sum(len(msg.get("content", "")) for msg in messages)
                model_lower = model.lower()

                if "gpt-5" in model_lower:
                    compression_threshold = 800000
                elif "gpt-4o" in model_lower:
                    compression_threshold = 350000
                elif "gemini-2.5" in model_lower:
                    compression_threshold = 1200000
                else:
                    compression_threshold = 200000

                if total_content_length > compression_threshold:
                    body["transforms"] = ["middle-out"]
                    self._logger.warning(
                        "middle_out_compression_applied",
                        extra={
                            "total_content_length": total_content_length,
                            "threshold": compression_threshold,
                            "model": model,
                        },
                    )

                # Make request
                started = time.perf_counter()
                try:
                    self._logger.debug(
                        "openrouter_request",
                        extra={
                            "model": model,
                            "attempt": attempt,
                            "messages_len": len(messages),
                            "structured_output": rf_included,
                            "rf_mode": rf_mode_current if rf_included else None,
                        },
                    )

                    if self._debug_payloads:
                        self._log_request_payload(headers, body, messages, rf_mode_current)

                    # Use connection pooling
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
                        self._log_response_payload(data)

                    status_code = resp.status_code

                    # Handle response format errors with graceful degradation
                    if status_code == 400 and rf_included and self._auto_fallback_structured:
                        err_dump = json.dumps(data).lower()
                        if "response_format" in err_dump:
                            # Try downgrading from json_schema to json_object
                            if rf_mode_current == "json_schema":
                                rf_mode_current = "json_object"
                                if self._audit:
                                    self._audit(
                                        "WARN",
                                        "openrouter_downgrade_json_schema_to_object",
                                        {"model": model, "request_id": request_id},
                                    )
                                self._logger.warning(
                                    "downgrade_response_format",
                                    extra={"model": model, "from": "json_schema", "to": "json_object"}
                                )
                                if attempt < self._max_retries:
                                    await self._sleep_backoff(attempt)
                                    continue

                            # If json_object also fails, disable structured outputs for this attempt
                            rf_included = False
                            structured_output_used = False
                            if self._audit:
                                self._audit(
                                    "WARN",
                                    "openrouter_disable_structured_outputs",
                                    {"model": model, "request_id": request_id},
                                )
                            self._logger.warning(
                                "disable_structured_outputs", extra={"model": model}
                            )
                            if attempt < self._max_retries:
                                await self._sleep_backoff(attempt)
                                continue

                    # Extract response content
                    text = None
                    usage = data.get("usage") or {}

                    try:
                        choices = data.get("choices") or []
                        if choices:
                            message_obj = choices[0].get("message", {}) or {}
                            text = self._extract_structured_content(message_obj, rf_included)
                    except Exception:
                        text = None

                    if isinstance(text, str):
                        last_response_text = text

                    # Calculate cost if enabled
                    cost_usd = None
                    if self._enable_stats:
                        try:
                            cost_usd = float(data.get("usage", {}).get("total_cost", 0.0))
                        except Exception:
                            cost_usd = None

                    # Prepare redacted headers
                    redacted_headers = dict(headers)
                    if "Authorization" in redacted_headers:
                        redacted_headers["Authorization"] = "REDACTED"

                    # Handle successful response
                    if status_code == 200:
                        # Validate structured output if expected
                        if rf_included and requested_rf:
                            text_str = text or ""
                            parsed = extract_json(text_str)

                            if parsed is not None:
                                try:
                                    text = json.dumps(parsed, ensure_ascii=False)
                                    last_response_text = text
                                except Exception:
                                    last_response_text = text_str
                            else:
                                # Invalid JSON with structured outputs - try fallback
                                if (self._auto_fallback_structured and
                                    rf_mode_current == "json_schema" and
                                    attempt < self._max_retries):

                                    rf_mode_current = "json_object"
                                    if self._audit:
                                        self._audit(
                                            "WARN",
                                            "openrouter_downgrade_on_200_invalid_json",
                                            {"model": model, "request_id": request_id},
                                        )
                                    await self._sleep_backoff(attempt)
                                    continue

                                # Treat as structured output parse error
                                last_error_text = "structured_output_parse_error"
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
                                break  # Try next model

                        # Success!
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
                                    "rf_mode": structured_output_mode_used,
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
                            structured_output_used=structured_output_used,
                            structured_output_mode=structured_output_mode_used,
                        )

                    # Handle various error codes
                    error_message = self._get_error_message(status_code, data)

                    # Non-retryable errors
                    if status_code in (400, 401, 402):
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
                        return self._build_error_result(
                            last_model_reported, text, data, usage, latency,
                            error_message, redacted_headers, messages
                        )

                    # 404: Try next model if available
                    if status_code == 404:
                        last_error_text = error_message
                        has_more_models = model != models_to_try[-1]
                        if self._audit:
                            self._audit(
                                "ERROR" if not has_more_models else "WARN",
                                "openrouter_not_found_try_fallback" if has_more_models else "openrouter_error",
                                {
                                    "attempt": attempt,
                                    "model": model,
                                    "status": status_code,
                                    "error": error_message,
                                    "request_id": request_id,
                                },
                            )
                        if has_more_models:
                            break  # Try next model

                        return self._build_error_result(
                            last_model_reported, text, data, usage, latency,
                            error_message, redacted_headers, messages
                        )

                    # Retryable errors (429, 5xx)
                    if status_code == 429 or status_code >= 500:
                        last_error_text = error_message
                        if attempt < self._max_retries:
                            # Handle rate limiting
                            if status_code == 429:
                                retry_after = resp.headers.get("retry-after")
                                if retry_after:
                                    try:
                                        retry_seconds = int(retry_after)
                                        await asyncio.sleep(retry_seconds)
                                        continue
                                    except (ValueError, TypeError):
                                        pass
                            await self._sleep_backoff(attempt)
                            continue
                        else:
                            break  # Try next model

                    # Unknown status code
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
                    return self._build_error_result(
                        last_model_reported, text, data, usage, latency,
                        error_message, redacted_headers, messages
                    )

                except Exception as e:
                    latency = int((time.perf_counter() - started) * 1000)
                    last_latency = latency
                    last_error_text = str(e)
                    self._logger.error(
                        "openrouter_exception",
                        extra={"error": str(e), "attempt": attempt, "model": model}
                    )
                    if attempt < self._max_retries:
                        await self._sleep_backoff(attempt)
                        continue
                    else:
                        break  # Try next model

            # Break if structured output parse error (don't try other models)
            if last_error_text == "structured_output_parse_error":
                break

            # Log fallback to next model
            if self._audit and model != models_to_try[-1]:
                next_model = models_to_try[models_to_try.index(model) + 1]
                self._audit(
                    "WARN",
                    "openrouter_fallback",
                    {
                        "from_model": model,
                        "to_model": next_model,
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
            endpoint="/api/v1/chat/completions",
            structured_output_used=structured_output_used,
            structured_output_mode=structured_output_mode_used,
        )

    def _build_error_result(
        self,
        model: str | None,
        text: str | None,
        data: dict | None,
        usage: dict,
        latency: int,
        error_message: str,
        headers: dict,
        messages: list[dict],
    ) -> LLMCallResult:
        """Build error result consistently."""
        return LLMCallResult(
            status="error",
            model=model,
            response_text=text,
            response_json=data,
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
        )

    def _log_request_payload(
        self, headers: dict, body: dict, messages: list[dict], rf_mode: str | None
    ) -> None:
        """Log request payload for debugging."""
        redacted_headers = dict(headers)
        if "Authorization" in redacted_headers:
            redacted_headers["Authorization"] = "REDACTED"

        preview_rf = body.get("response_format") or {}
        rf_type = preview_rf.get("type") if isinstance(preview_rf, dict) else None

        # Calculate content lengths
        content_lengths = [len(msg.get("content", "")) for msg in messages]
        total_content = sum(content_lengths)

        # Show truncated messages for debug
        debug_messages = []
        for i, msg in enumerate(messages[:3]):
            debug_msg = dict(msg)
            content = debug_msg.get("content", "")
            if len(content) > 200:
                debug_msg["content"] = content[:100] + f"... [+{len(content) - 100} chars]"
            debug_msg["content_length"] = str(len(content))
            debug_messages.append(debug_msg)

        self._logger.debug(
            "openrouter_request_payload",
            extra={
                "headers": redacted_headers,
                "body_preview": {
                    "model": body.get("model"),
                    "messages": debug_messages,
                    "temperature": body.get("temperature"),
                    "response_format_type": rf_type,
                    "response_format_mode": rf_mode,
                    "total_content_length": total_content,
                    "content_lengths": content_lengths,
                    "transforms": body.get("transforms"),
                },
            },
        )

    def _log_response_payload(self, data: dict) -> None:
        """Log response payload for debugging."""
        try:
            preview = data
            # Truncate large response content
            if isinstance(preview, dict) and "choices" in preview:
                choices = preview.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    choice = choices[0]
                    if "message" in choice and isinstance(choice["message"], dict):
                        msg_content = choice["message"].get("content")
                        if msg_content and isinstance(msg_content, str):
                            truncated_content = truncate_log_content(
                                msg_content, self._log_truncate_length
                            )
                            choice["message"]["content"] = truncated_content

            self._logger.debug("openrouter_response_payload", extra={"preview": preview})
        except Exception:
            pass

    async def _sleep_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        import random

        base_delay = max(0.0, self._backoff_base * (2**attempt))
        jitter = 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(base_delay * jitter)

    async def _ensure_structured_supported_models(self) -> None:
        """Fetch and cache models supporting structured outputs."""
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

                models: set[str] = set()
                data_array = []

                if isinstance(payload, dict):
                    if isinstance(payload.get("data"), list):
                        data_array = payload.get("data", [])
                    elif isinstance(payload.get("models"), list):
                        data_array = payload.get("models", [])

                for item in data_array:
                    try:
                        if isinstance(item, dict):
                            model_id = (
                                item.get("id") or
                                item.get("name") or
                                item.get("model")
                            )
                            if isinstance(model_id, str) and model_id:
                                models.add(model_id)
                    except Exception:
                        continue

                if models:
                    self._structured_supported_models = models
                    self._logger.debug(
                        "structured_outputs_capabilities_loaded",
                        extra={"models_count": len(models)}
                    )
                else:
                    # Keep existing cache or use known models as fallback
                    if self._structured_supported_models is None:
                        self._structured_supported_models = self._known_structured_models.copy()
                        self._logger.warning(
                            "using_fallback_structured_models",
                            extra={"models_count": len(self._structured_supported_models)}
                        )

                self._capabilities_last_load = now

        except Exception as e:
            self._capabilities_last_load = now
            # Use known models as fallback
            if self._structured_supported_models is None:
                self._structured_supported_models = self._known_structured_models.copy()

            self._logger.warning(
                "openrouter_capabilities_probe_failed",
                extra={"error": str(e), "using_fallback": True}
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
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self._logger.error("openrouter_models_error", extra={"error": str(e)})
            raise

    async def get_structured_models(self) -> set[str]:
        """Get set of models that support structured outputs."""
        await self._ensure_structured_supported_models()
        return self._structured_supported_models or set()


# Utility function for backoff (kept for compatibility)
async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Exponential backoff with light jitter."""
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
