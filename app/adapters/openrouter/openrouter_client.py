"""Refactored OpenRouter client using modular components."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.adapters.openrouter.error_handler import ErrorHandler
from app.adapters.openrouter.model_capabilities import ModelCapabilities
from app.adapters.openrouter.payload_logger import PayloadLogger
from app.adapters.openrouter.request_builder import RequestBuilder
from app.adapters.openrouter.response_processor import ResponseProcessor
from app.models.llm.llm_models import ChatRequest, LLMCallResult


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
        # Validate core parameters
        self._validate_init_params(
            api_key,
            model,
            fallback_models,
            http_referer,
            x_title,
            timeout_sec,
            max_retries,
            backoff_base,
            structured_output_mode,
        )

        # Store configuration
        self._api_key = api_key
        self._model = model
        self._fallback_models = self._validate_fallback_models(fallback_models)
        self._timeout = int(timeout_sec)
        self._base_url = "https://openrouter.ai/api/v1"
        self._enable_structured_outputs = enable_structured_outputs

        # Initialize components
        self.request_builder = RequestBuilder(
            api_key=api_key,
            http_referer=http_referer,
            x_title=x_title,
            provider_order=provider_order,
            enable_structured_outputs=enable_structured_outputs,
            structured_output_mode=structured_output_mode,
            require_parameters=require_parameters,
        )

        self.response_processor = ResponseProcessor(
            enable_stats=enable_stats,
        )

        self.model_capabilities = ModelCapabilities(
            api_key=api_key,
            base_url=self._base_url,
            http_referer=http_referer,
            x_title=x_title,
            timeout=self._timeout,
        )

        self.error_handler = ErrorHandler(
            max_retries=max_retries,
            backoff_base=backoff_base,
            audit=audit,
            auto_fallback_structured=auto_fallback_structured,
        )

        self.payload_logger = PayloadLogger(
            debug_payloads=debug_payloads,
            log_truncate_length=log_truncate_length,
        )

    def _get_error_message(self, status_code: int, data: dict[str, Any] | None) -> str:
        """Return a human-friendly error message for an HTTP status.

        This mirrors the expectations asserted in tests by mapping common
        statuses to stable, descriptive messages and appending any message
        provided by the API payload when present.
        """
        # Extract optional message from payload (string or nested {error: {message}})
        payload_message: str | None = None
        if data:
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                if isinstance(msg, str) and msg:
                    payload_message = msg
            elif isinstance(err, str) and err:
                payload_message = err

        base_map: dict[int, str] = {
            400: "Invalid or missing request parameters",
            401: "Authentication failed",
            402: "Insufficient account balance",
            404: "Requested resource not found",
            429: "Rate limit exceeded",
        }

        if status_code >= 500:
            base = "Internal server error"
        else:
            base = base_map.get(status_code, f"HTTP {status_code} error")

        if payload_message:
            return f"{base}: {payload_message}"
        return base

    def _validate_init_params(
        self,
        api_key: str,
        model: str,
        fallback_models: list[str] | tuple[str, ...] | None,
        http_referer: str | None,
        x_title: str | None,
        timeout_sec: int,
        max_retries: int,
        backoff_base: float,
        structured_output_mode: str,
    ) -> None:
        """Validate initialization parameters."""
        # Security: Validate API key presence
        if not api_key or not isinstance(api_key, str):
            raise ValueError("API key is required")

        # Security: Validate model
        if not model or not isinstance(model, str):
            raise ValueError("Model is required")
        if len(model) > 100:
            raise ValueError("Model name too long")

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
        if not isinstance(backoff_base, int | float) or backoff_base < 0:
            raise ValueError("Backoff base must be non-negative")

        # Validate structured output settings
        if structured_output_mode not in {"json_schema", "json_object"}:
            raise ValueError("Structured output mode must be 'json_schema' or 'json_object'")

    def _validate_fallback_models(
        self, fallback_models: list[str] | tuple[str, ...] | None
    ) -> list[str]:
        """Validate and return fallback models."""
        validated_fallbacks = []
        if fallback_models:
            for fallback in fallback_models:
                if isinstance(fallback, str) and fallback and len(fallback) <= 100:
                    validated_fallbacks.append(fallback)
        return validated_fallbacks

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
        # Create and validate request
        request = ChatRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            request_id=request_id,
            response_format=response_format,
            model_override=model_override,
        )

        self.request_builder.validate_chat_request(request)
        sanitized_messages = self.request_builder.sanitize_messages(messages)

        # Determine models to try
        primary_model = model_override if model_override else self._model
        models_to_try = self.model_capabilities.build_model_fallback_list(
            primary_model, self._fallback_models, response_format, self._enable_structured_outputs
        )

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
            # Skip models that don't support structured outputs if required
            if response_format and self._enable_structured_outputs:
                await self.model_capabilities.ensure_structured_supported_models()
                if not self.model_capabilities.supports_structured_outputs(model):
                    self.error_handler.log_skip_model(model, "no_structured_outputs", request_id)
                    continue

            # Determine response format mode for this model
            rf_mode_current = self.request_builder._structured_output_mode
            requested_rf = response_format if isinstance(response_format, dict) else None

            # Retry logic for each model
            for attempt in range(self.error_handler._max_retries + 1):
                self.error_handler.log_attempt(attempt, model, request_id)

                # Build request components
                headers = self.request_builder.build_headers()
                body = self.request_builder.build_request_body(
                    model, sanitized_messages, request, requested_rf
                )

                # Apply content compression if needed
                should_compress, transform_type = self.request_builder.should_apply_compression(
                    sanitized_messages, model
                )
                if should_compress and transform_type:
                    body["transforms"] = [transform_type]
                    total_length = sum(len(msg.get("content", "")) for msg in sanitized_messages)
                    self.payload_logger.log_compression_applied(total_length, 200000, model)

                # Check if response format is included
                rf_included = "response_format" in body
                if rf_included:
                    structured_output_used = True
                    structured_output_mode_used = rf_mode_current

                # Make request
                started = time.perf_counter()
                try:
                    self.payload_logger.log_request(
                        model, attempt, len(sanitized_messages), rf_included, rf_mode_current
                    )

                    if self.payload_logger._debug_payloads:
                        self.payload_logger.log_request_payload(
                            headers, body, sanitized_messages, rf_mode_current
                        )

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

                    self.payload_logger.log_response(resp.status_code, latency, last_model_reported)

                    if self.payload_logger._debug_payloads:
                        self.payload_logger.log_response_payload(data)

                    status_code = resp.status_code

                    # Handle response format errors with graceful degradation
                    if self.response_processor.should_downgrade_response_format(
                        status_code, data, rf_included
                    ):
                        should_downgrade, new_mode = (
                            self.error_handler.should_downgrade_response_format(
                                status_code, data, rf_mode_current, rf_included, attempt
                            )
                        )
                        if should_downgrade:
                            if new_mode:
                                rf_mode_current = new_mode
                                self.error_handler.log_response_format_downgrade(
                                    model, "json_schema", "json_object", request_id
                                )
                            else:
                                rf_included = False
                                structured_output_used = False
                                self.error_handler.log_structured_outputs_disabled(
                                    model, request_id
                                )

                            if attempt < self.error_handler._max_retries:
                                await self.error_handler.sleep_backoff(attempt)
                                continue

                    # Extract response content
                    text, usage, cost_usd = self.response_processor.extract_response_data(
                        data, rf_included
                    )
                    if isinstance(text, str):
                        last_response_text = text

                    # Prepare redacted headers
                    redacted_headers = self.request_builder.get_redacted_headers(headers)

                    # Handle successful response
                    if status_code == 200:
                        # Validate structured output if expected
                        if rf_included and requested_rf:
                            is_valid, processed_text = (
                                self.response_processor.validate_structured_response(
                                    text, rf_included, requested_rf
                                )
                            )
                            if not is_valid:
                                # Try fallback for invalid JSON
                                if (
                                    rf_mode_current == "json_schema"
                                    and attempt < self.error_handler._max_retries
                                ):
                                    rf_mode_current = "json_object"
                                    self.error_handler.log_response_format_downgrade(
                                        model, "json_schema", "json_object", request_id
                                    )
                                    await self.error_handler.sleep_backoff(attempt)
                                    continue

                                # Treat as structured output parse error
                                last_error_text = "structured_output_parse_error"
                                last_response_text = processed_text or None
                                break  # Try next model
                            else:
                                text = processed_text

                        # Success!
                        self.error_handler.log_success(
                            attempt,
                            model,
                            status_code,
                            latency,
                            structured_output_used,
                            structured_output_mode_used,
                            request_id,
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
                            request_messages=sanitized_messages,
                            endpoint="/api/v1/chat/completions",
                            structured_output_used=structured_output_used,
                            structured_output_mode=structured_output_mode_used,
                        )

                    # Handle various error codes
                    error_message = self.response_processor.get_error_message(status_code, data)

                    # Non-retryable errors
                    if self.error_handler.is_non_retryable_error(status_code):
                        self.error_handler.log_error(
                            attempt, model, status_code, error_message, request_id
                        )
                        return self.error_handler.build_error_result(
                            last_model_reported,
                            text,
                            data,
                            usage,
                            latency,
                            error_message,
                            redacted_headers,
                            sanitized_messages,
                        )

                    # 404: Try next model if available
                    if self.error_handler.should_try_next_model(status_code):
                        last_error_text = error_message
                        has_more_models = model != models_to_try[-1]
                        severity = "WARN" if has_more_models else "ERROR"
                        self.error_handler.log_error(
                            attempt, model, status_code, error_message, request_id, severity
                        )
                        if has_more_models:
                            break  # Try next model

                        return self.error_handler.build_error_result(
                            last_model_reported,
                            text,
                            data,
                            usage,
                            latency,
                            error_message,
                            redacted_headers,
                            sanitized_messages,
                        )

                    # Retryable errors
                    if self.error_handler.should_retry(status_code, attempt):
                        last_error_text = error_message
                        if status_code == 429:
                            await self.error_handler.handle_rate_limit(resp.headers)
                        else:
                            await self.error_handler.sleep_backoff(attempt)
                        continue
                    else:
                        break  # Try next model

                    # Unknown status code
                    self.error_handler.log_error(
                        attempt, model, status_code, error_message, request_id
                    )
                    return self.error_handler.build_error_result(
                        last_model_reported,
                        text,
                        data,
                        usage,
                        latency,
                        error_message,
                        redacted_headers,
                        sanitized_messages,
                    )

                except Exception as e:
                    latency = int((time.perf_counter() - started) * 1000)
                    last_latency = latency
                    last_error_text = str(e)
                    if attempt < self.error_handler._max_retries:
                        await self.error_handler.sleep_backoff(attempt)
                        continue
                    else:
                        break  # Try next model

            # Break if structured output parse error (don't try other models)
            if last_error_text == "structured_output_parse_error":
                break

            # Log fallback to next model
            if model != models_to_try[-1]:
                next_model = models_to_try[models_to_try.index(model) + 1]
                self.error_handler.log_fallback(model, next_model, request_id)

        # All models exhausted
        redacted_headers = self.request_builder.get_redacted_headers(
            {"Authorization": "REDACTED", "Content-Type": "application/json"}
        )

        self.error_handler.log_exhausted(
            models_to_try, self.error_handler._max_retries + 1, last_error_text, request_id
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
            request_messages=sanitized_messages,
            endpoint="/api/v1/chat/completions",
            structured_output_used=structured_output_used,
            structured_output_mode=structured_output_mode_used,
        )

    async def get_models(self) -> dict[str, Any]:
        """Get available models from OpenRouter API."""
        return await self.model_capabilities.get_models()

    async def get_structured_models(self) -> set[str]:
        """Get set of models that support structured outputs."""
        return await self.model_capabilities.get_structured_models()


# Utility function for backoff (kept for compatibility)
async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Exponential backoff with light jitter."""
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    import asyncio

    await asyncio.sleep(base_delay * jitter)
