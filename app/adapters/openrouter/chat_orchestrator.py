"""Chat orchestration: model fallback loop, retry logic, and request execution.

Extracted from OpenRouterClient to separate HTTP pool management from
chat request orchestration. This module contains the model x attempt
retry loop, request building, response handling, and error recovery.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.models.llm.llm_models import ChatRequest, LLMCallResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.openrouter.chat_state import ChatState
    from app.adapters.openrouter.error_handler import ErrorHandler
    from app.adapters.openrouter.model_capabilities import ModelCapabilities
    from app.adapters.openrouter.payload_logger import PayloadLogger
    from app.adapters.openrouter.request_builder import RequestBuilder
    from app.adapters.openrouter.response_processor import ResponseProcessor
    from app.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    """Orchestrates model fallback, retry, and structured output downgrade logic.

    Receives references to the existing helper objects (request_builder,
    response_processor, error_handler, etc.) and owns the model x attempt
    retry loop that was previously inlined in OpenRouterClient.chat().
    """

    def __init__(
        self,
        *,
        request_builder: RequestBuilder,
        response_processor: ResponseProcessor,
        error_handler: ErrorHandler,
        model_capabilities: ModelCapabilities,
        payload_logger: PayloadLogger,
        circuit_breaker: CircuitBreaker | None,
        max_response_size_bytes: int,
        price_input_per_1k: float | None,
        price_output_per_1k: float | None,
        get_error_message: Callable[[int, dict[str, Any] | None], str],
    ) -> None:
        self._request_builder = request_builder
        self._response_processor = response_processor
        self._error_handler = error_handler
        self._model_capabilities = model_capabilities
        self._payload_logger = payload_logger
        self._circuit_breaker = circuit_breaker
        self._max_response_size_bytes = max_response_size_bytes
        self._price_input_per_1k = price_input_per_1k
        self._price_output_per_1k = price_output_per_1k
        self._get_error_message = get_error_message

    async def execute(
        self,
        client: httpx.AsyncClient,
        request: ChatRequest,
        sanitized_messages: list[dict[str, str]],
        models_to_try: list[str],
        state: ChatState,
        primary_model: str,
        enable_structured_outputs: bool,
    ) -> LLMCallResult:
        """Execute the model x attempt retry loop.

        Returns an LLMCallResult (success or error).
        """
        response_format = state.response_format_initial

        try:
            for model_idx, model in enumerate(models_to_try):
                # Skip models that don't support structured outputs if required
                if response_format and enable_structured_outputs:
                    try:
                        await self._model_capabilities.ensure_structured_supported_models()
                        if not self._model_capabilities.supports_structured_outputs(model):
                            if model == primary_model:
                                self._error_handler.log_skip_model(
                                    model, "no_structured_outputs_primary", request.request_id
                                )
                                state.structured_output_used = False
                                state.structured_output_mode_used = None
                            else:
                                self._error_handler.log_skip_model(
                                    model, "no_structured_outputs", request.request_id
                                )
                                continue
                    except Exception as e:
                        raise_if_cancelled(e)
                        logger.warning("Failed to check model capabilities: %s", e)

                # Reset mode for each new model
                state.rf_mode_current = state.builder_rf_mode_original
                state.response_format_current = state.response_format_initial

                # Retry logic for each model
                for attempt in range(self._error_handler._max_retries + 1):
                    try:
                        result = await self._attempt_request(
                            client=client,
                            model=model,
                            attempt=attempt,
                            sanitized_messages=sanitized_messages,
                            request=request,
                            state=state,
                        )

                        # Handle successful result
                        if result.get("success"):
                            self._request_builder._structured_output_mode = (
                                state.builder_rf_mode_original
                            )
                            if self._circuit_breaker:
                                self._circuit_breaker.record_success()
                            return result["llm_result"]

                        # Handle retry/fallback logic
                        if result.get("should_retry"):
                            state.update_retry_state(result)

                            # Handle truncation recovery
                            truncation_recovery = result.get("truncation_recovery")
                            if truncation_recovery:
                                new_max = truncation_recovery.get("suggested_max_tokens")
                                if new_max and (
                                    not request.max_tokens or new_max > request.max_tokens
                                ):
                                    logger.info(
                                        "truncation_recovery_increasing_max_tokens",
                                        extra={
                                            "model": model,
                                            "original_max": request.max_tokens,
                                            "new_max": new_max,
                                            "attempt": attempt + 1,
                                        },
                                    )
                                    request = ChatRequest(
                                        messages=request.messages,
                                        temperature=request.temperature,
                                        max_tokens=new_max,
                                        top_p=request.top_p,
                                        stream=request.stream,
                                        request_id=request.request_id,
                                        response_format=request.response_format,
                                        model_override=request.model_override,
                                    )

                            if result.get("backoff_needed"):
                                await self._error_handler.sleep_backoff(attempt)
                            continue

                        # Update state for potential fallback
                        state.update_from_result(result)

                        if result.get("should_try_next_model"):
                            break

                        # Return error result
                        if result.get("error_result"):
                            self._request_builder._structured_output_mode = (
                                state.builder_rf_mode_original
                            )
                            if self._circuit_breaker:
                                self._circuit_breaker.record_failure()
                            return result["error_result"]

                    except httpx.TimeoutException as e:
                        state.last_error_text = f"Request timeout: {e!s}"
                        state.last_error_context = {
                            "status_code": None,
                            "message": "Request timeout",
                            "api_error": str(e),
                        }
                        if attempt < self._error_handler._max_retries:
                            await self._error_handler.sleep_backoff(attempt)
                            continue
                        break
                    except httpx.ConnectError as e:
                        state.last_error_text = f"Connection error: {e!s}"
                        state.last_error_context = {
                            "status_code": None,
                            "message": "Connection failed",
                            "api_error": str(e),
                        }
                        if attempt < self._error_handler._max_retries:
                            await self._error_handler.sleep_backoff(attempt)
                            continue
                        break
                    except httpx.HTTPStatusError as e:
                        state.last_error_text = f"HTTP {e.response.status_code} error: {e!s}"
                        state.last_error_context = {
                            "status_code": e.response.status_code,
                            "message": "HTTP status error",
                            "api_error": str(e),
                        }
                        if attempt < self._error_handler._max_retries:
                            await self._error_handler.sleep_backoff(attempt)
                            continue
                        break
                    except Exception as e:
                        raise_if_cancelled(e)
                        state.last_error_text = f"Unexpected error: {e!s}"
                        state.last_error_context = {
                            "status_code": None,
                            "message": "Client exception",
                            "api_error": str(e),
                        }
                        if attempt < self._error_handler._max_retries:
                            await self._error_handler.sleep_backoff(attempt)
                            continue
                        break

                # On structured output parse error, try next model
                if state.structured_parse_error:
                    logger.info(
                        "structured_parse_error_trying_next_model",
                        extra={
                            "model": model,
                            "request_id": request.request_id,
                            "models_remaining": len(models_to_try) - model_idx - 1,
                        },
                    )

                # Log fallback to next model
                if model_idx < len(models_to_try) - 1:
                    next_model = models_to_try[model_idx + 1]
                    self._error_handler.log_fallback(model, next_model, request.request_id)

        except Exception as e:
            raise_if_cancelled(e)
            state.last_error_text = f"Critical error: {e!s}"
            state.last_error_context = {
                "status_code": None,
                "message": "Critical client error",
                "api_error": str(e),
                "error_type": "critical",
            }

        finally:
            self._request_builder._structured_output_mode = state.builder_rf_mode_original

        # All models exhausted
        return self._build_exhausted_result(models_to_try, sanitized_messages, state)

    def _build_exhausted_result(
        self,
        models_to_try: list[str],
        sanitized_messages: list[dict[str, str]],
        state: ChatState,
    ) -> LLMCallResult:
        """Build the final error result when all models and retries are exhausted."""
        redacted_headers = self._request_builder.get_redacted_headers(
            {"Authorization": "REDACTED", "Content-Type": "application/json"}
        )

        self._error_handler.log_exhausted(
            models_to_try,
            self._error_handler._max_retries + 1,
            state.last_error_text,
            None,
        )

        if self._circuit_breaker:
            self._circuit_breaker.record_failure()

        return LLMCallResult(
            status="error",
            model=state.last_model_reported,
            response_text=state.last_response_text,
            response_json=state.last_data,
            openrouter_response_text=state.last_response_text,
            openrouter_response_json=state.last_data,
            tokens_prompt=None,
            tokens_completion=None,
            cost_usd=None,
            latency_ms=state.last_latency,
            error_text=(
                "structured_output_parse_error"
                if state.structured_parse_error
                else (state.last_error_text or "All retries and fallbacks exhausted")
            ),
            request_headers=redacted_headers,
            request_messages=sanitized_messages,
            endpoint="/api/v1/chat/completions",
            structured_output_used=state.structured_output_used,
            structured_output_mode=state.structured_output_mode_used,
            error_context=state.last_error_context,
        )

    # ------------------------------------------------------------------
    # Single-attempt execution
    # ------------------------------------------------------------------

    async def _attempt_request(
        self,
        client: httpx.AsyncClient,
        model: str,
        attempt: int,
        sanitized_messages: list[dict[str, str]],
        request: ChatRequest,
        state: ChatState,
    ) -> dict[str, Any]:
        """Execute a single request attempt with comprehensive error handling."""
        self._error_handler.log_attempt(attempt, model, request.request_id)

        cacheable_messages = self._request_builder.build_cacheable_messages(
            sanitized_messages, model
        )

        # Build request components
        self._request_builder._structured_output_mode = state.rf_mode_current
        headers = self._request_builder.build_headers()
        body = self._request_builder.build_request_body(
            model, cacheable_messages, request, state.response_format_current
        )

        if state.rf_mode_current == "json_object" and "response_format" in body:
            body["response_format"] = {"type": "json_object"}

        # Apply content compression if needed
        should_compress, transform_type = self._request_builder.should_apply_compression(
            cacheable_messages, model
        )
        if should_compress and transform_type:
            body["transforms"] = [transform_type]
            total_length = sum(
                len(msg.get("content", ""))
                if isinstance(msg.get("content"), str)
                else sum(
                    len(p.get("text", "")) for p in msg.get("content", []) if isinstance(p, dict)
                )
                for msg in cacheable_messages
            )
            self._payload_logger.log_compression_applied(total_length, 200000, model)

        rf_included = "response_format" in body
        structured_output_used = rf_included
        structured_output_mode_used = state.rf_mode_current if rf_included else None

        started = time.perf_counter()
        try:
            self._payload_logger.log_request(
                model=model,
                attempt=attempt,
                request_id=request.request_id,
                message_lengths=state.message_lengths,
                message_roles=state.message_roles,
                total_chars=state.total_chars,
                structured_output=rf_included,
                rf_mode=state.rf_mode_current,
                transforms=body.get("transforms"),
            )

            if self._payload_logger._debug_payloads:
                self._payload_logger.log_request_payload(
                    headers, body, cacheable_messages, state.rf_mode_current
                )

            resp = await client.post(
                "/chat/completions",
                headers=headers,
                json=body,
            )

            # Validate response size
            try:
                await validate_response_size(resp, self._max_response_size_bytes, "OpenRouter")
            except ResponseSizeError as size_exc:
                latency = int((time.perf_counter() - started) * 1000)
                return {
                    "success": False,
                    "error_text": f"Response too large: {size_exc}",
                    "latency": latency,
                    "should_try_next_model": True,
                }

            latency = int((time.perf_counter() - started) * 1000)

            try:
                data = resp.json()
            except Exception as e:
                raise_if_cancelled(e)
                return {
                    "success": False,
                    "error_text": f"Failed to parse JSON response: {e}",
                    "latency": latency,
                    "should_try_next_model": True,
                }

            if self._payload_logger._debug_payloads:
                self._payload_logger.log_response_payload(data)

            status_code = resp.status_code
            model_reported = data.get("model", model) if isinstance(data, dict) else model

            if status_code == 200:
                return await self._handle_successful_response(
                    data=data,
                    rf_included=rf_included,
                    state=state,
                    model=model,
                    model_reported=model_reported,
                    latency=latency,
                    attempt=attempt,
                    request_id=request.request_id,
                    structured_output_used=structured_output_used,
                    structured_output_mode_used=structured_output_mode_used,
                    headers=headers,
                    sanitized_messages=sanitized_messages,
                    max_tokens=request.max_tokens,
                )

            return await self._handle_error_response(
                status_code=status_code,
                data=data,
                resp=resp,
                rf_included=rf_included,
                state=state,
                model=model,
                model_reported=model_reported,
                latency=latency,
                attempt=attempt,
                request_id=request.request_id,
                headers=headers,
                sanitized_messages=sanitized_messages,
            )

        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "success": False,
                "error_text": "Request timeout",
                "latency": latency,
                "should_retry": attempt < self._error_handler._max_retries,
                "backoff_needed": True,
            }
        except Exception as e:
            raise_if_cancelled(e)
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "success": False,
                "error_text": str(e),
                "latency": latency,
                "should_retry": attempt < self._error_handler._max_retries,
                "backoff_needed": True,
            }

    # ------------------------------------------------------------------
    # Response handlers
    # ------------------------------------------------------------------

    async def _handle_successful_response(
        self,
        data: dict[str, Any],
        rf_included: bool,
        state: ChatState,
        model: str,
        model_reported: str,
        latency: int,
        attempt: int,
        request_id: int | None,
        structured_output_used: bool,
        structured_output_mode_used: str | None,
        headers: dict[str, str],
        sanitized_messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Handle successful API response."""
        text, usage, cost_usd = self._response_processor.extract_response_data(data, rf_included)

        truncated, truncated_finish, truncated_native = (
            self._response_processor.is_completion_truncated(data)
        )

        if truncated:
            self._error_handler.log_truncated_completion(
                model, truncated_finish, truncated_native, request_id
            )

            current_max = max_tokens or 8192
            suggested_max = min(int(current_max * 1.5), 32768)

            if rf_included and state.response_format_current:
                if state.rf_mode_current == "json_schema":
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": "json_object",
                        "new_response_format": {"type": "json_object"},
                        "backoff_needed": True,
                        "structured_output_used": True,
                        "structured_output_mode_used": "json_object",
                        "truncation_recovery": {
                            "original_max_tokens": current_max,
                            "suggested_max_tokens": suggested_max,
                        },
                    }
                if state.rf_mode_current == "json_object":
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": state.rf_mode_current,
                        "new_response_format": None,
                        "backoff_needed": True,
                        "structured_output_used": False,
                        "structured_output_mode_used": None,
                        "truncation_recovery": {
                            "original_max_tokens": current_max,
                            "suggested_max_tokens": suggested_max,
                        },
                    }

            if attempt < self._error_handler._max_retries:
                return {
                    "success": False,
                    "should_retry": True,
                    "backoff_needed": True,
                    "truncation_recovery": {
                        "original_max_tokens": current_max,
                        "suggested_max_tokens": suggested_max,
                    },
                }

            return {
                "success": False,
                "error_text": "completion_truncated",
                "response_text": text if isinstance(text, str) else None,
                "should_try_next_model": True,
                "truncation_recovery": {
                    "original_max_tokens": current_max,
                    "suggested_max_tokens": suggested_max,
                },
            }

        # Validate structured output if expected
        if rf_included and state.response_format_current:
            is_valid, processed_text = self._response_processor.validate_structured_response(
                text, rf_included, state.response_format_current
            )
            if not is_valid:
                if (
                    state.rf_mode_current == "json_schema"
                    and attempt < self._error_handler._max_retries
                ):
                    logger.warning(
                        "structured_output_downgrading_json_schema_to_json_object",
                        extra={"model": model, "attempt": attempt + 1},
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": "json_object",
                        "new_response_format": {"type": "json_object"},
                        "backoff_needed": True,
                    }

                if (
                    state.rf_mode_current == "json_object"
                    and attempt < self._error_handler._max_retries
                ):
                    logger.warning(
                        "structured_output_disabling_after_json_object_failure",
                        extra={"model": model, "attempt": attempt + 1},
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": None,
                        "new_response_format": None,
                        "backoff_needed": True,
                    }

                return {
                    "success": False,
                    "error_text": "structured_output_parse_error",
                    "response_text": processed_text or None,
                    "structured_parse_error": True,
                    "should_try_next_model": True,
                }
            text = processed_text

        # Extract finish reason and tokens
        finish_reason = None
        native_finish = None
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices:
            first_choice = choices[0] or {}
            if isinstance(first_choice, dict):
                finish_reason = first_choice.get("finish_reason")
                native_finish = first_choice.get("native_finish_reason")

        tokens_prompt = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        tokens_completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
        tokens_total = usage.get("total_tokens") if isinstance(usage, dict) else None

        cache_metrics = self._response_processor.extract_cache_metrics(data)
        if cache_metrics.cache_hit or cache_metrics.cache_creation_tokens > 0:
            logger.info(
                "prompt_cache_metrics",
                extra={
                    "model": model_reported,
                    "cache_read_tokens": cache_metrics.cache_read_tokens,
                    "cache_creation_tokens": cache_metrics.cache_creation_tokens,
                    "cache_discount": cache_metrics.cache_discount,
                    "cache_hit": cache_metrics.cache_hit,
                    "request_id": request_id,
                },
            )

        # Estimate cost if not provided by API
        if cost_usd is None and tokens_prompt is not None and tokens_completion is not None:
            if self._price_input_per_1k is not None and self._price_output_per_1k is not None:
                try:
                    cost_usd = (float(tokens_prompt) / 1000.0) * self._price_input_per_1k + (
                        float(tokens_completion) / 1000.0
                    ) * self._price_output_per_1k
                except Exception:
                    cost_usd = None

        self._payload_logger.log_response(
            status=200,
            latency_ms=latency,
            model=model_reported,
            attempt=attempt,
            request_id=request_id,
            truncated=truncated,
            finish_reason=finish_reason,
            native_finish_reason=native_finish,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            tokens_total=tokens_total,
            cost_usd=cost_usd,
            structured_output=rf_included,
            rf_mode=state.rf_mode_current,
        )

        self._error_handler.log_success(
            attempt,
            model,
            200,
            latency,
            structured_output_used,
            structured_output_mode_used,
            request_id,
        )

        redacted_headers = self._request_builder.get_redacted_headers(headers)

        return {
            "success": True,
            "llm_result": LLMCallResult(
                status="ok",
                model=model_reported,
                response_text=text,
                response_json=data,
                openrouter_response_text=text,
                openrouter_response_json=data,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                cost_usd=cost_usd,
                latency_ms=latency,
                error_text=None,
                request_headers=redacted_headers,
                request_messages=sanitized_messages,
                endpoint="/api/v1/chat/completions",
                structured_output_used=structured_output_used,
                structured_output_mode=structured_output_mode_used,
                cache_read_tokens=(
                    cache_metrics.cache_read_tokens if cache_metrics.cache_read_tokens > 0 else None
                ),
                cache_creation_tokens=(
                    cache_metrics.cache_creation_tokens
                    if cache_metrics.cache_creation_tokens > 0
                    else None
                ),
                cache_discount=cache_metrics.cache_discount,
            ),
        }

    async def _handle_error_response(
        self,
        status_code: int,
        data: dict[str, Any],
        resp: httpx.Response,
        rf_included: bool,
        state: ChatState,
        model: str,
        model_reported: str,
        latency: int,
        attempt: int,
        request_id: int | None,
        headers: dict[str, str],
        sanitized_messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Handle error responses with appropriate retry/fallback logic."""
        if self._response_processor.should_downgrade_response_format(
            status_code, data, rf_included
        ):
            should_downgrade, new_mode = self._error_handler.should_downgrade_response_format(
                status_code, data, state.rf_mode_current, rf_included, attempt
            )
            if should_downgrade:
                if new_mode:
                    self._error_handler.log_response_format_downgrade(
                        model,
                        "json_schema",
                        new_mode,
                        request_id,
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": new_mode,
                        "new_response_format": (
                            {"type": "json_object"} if new_mode == "json_object" else None
                        ),
                        "backoff_needed": True,
                    }
                self._error_handler.log_structured_outputs_disabled(model, request_id)
                return {
                    "success": False,
                    "should_retry": True,
                    "new_rf_mode": state.rf_mode_current,
                    "new_response_format": None,
                    "structured_output_used": False,
                    "structured_output_mode_used": None,
                    "backoff_needed": True,
                }

        text, usage, _cost_usd = self._response_processor.extract_response_data(data, rf_included)
        error_context = self._response_processor.get_error_context(status_code, data)
        error_message = error_context["message"]

        redacted_headers = self._request_builder.get_redacted_headers(headers)

        if self._error_handler.is_non_retryable_error(status_code):
            error_message = self._get_error_message(status_code, data)
            return {
                "success": False,
                "error_result": self._error_handler.build_error_result(
                    model_reported,
                    text,
                    data,
                    usage,
                    latency,
                    error_message,
                    redacted_headers,
                    sanitized_messages,
                    error_context=error_context,
                ),
            }

        if self._error_handler.should_try_next_model(status_code):
            api_error_lower = (
                str(error_context.get("api_error", "")).lower()
                if isinstance(error_context, dict)
                else ""
            )

            if (
                rf_included
                and state.response_format_current
                and (
                    status_code == 404
                    or (
                        isinstance(error_message, str)
                        and "no endpoints found" in error_message.lower()
                    )
                    or "no endpoints found" in api_error_lower
                    or "does not support structured" in api_error_lower
                )
            ):
                if state.rf_mode_current == "json_schema":
                    self._error_handler.log_response_format_downgrade(
                        model,
                        "json_schema",
                        "json_object",
                        request_id,
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": "json_object",
                        "new_response_format": {"type": "json_object"},
                        "backoff_needed": True,
                    }
                if state.rf_mode_current == "json_object":
                    self._error_handler.log_structured_outputs_disabled(model, request_id)
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": state.rf_mode_current,
                        "new_response_format": None,
                        "structured_output_used": False,
                        "structured_output_mode_used": None,
                        "backoff_needed": True,
                    }

            self._error_handler.log_error(
                attempt, model, status_code, error_message, request_id, "WARN"
            )
            return {
                "success": False,
                "error_text": error_message,
                "data": data,
                "latency": latency,
                "model_reported": model_reported,
                "error_context": error_context,
                "should_try_next_model": True,
            }

        if self._error_handler.should_retry(status_code, attempt):
            if status_code == 429:
                await self._error_handler.handle_rate_limit(resp.headers)
            return {
                "success": False,
                "should_retry": True,
                "backoff_needed": status_code != 429,
                "error_text": error_message,
                "error_context": error_context,
            }

        self._error_handler.log_error(attempt, model, status_code, error_message, request_id)
        return {
            "success": False,
            "error_text": error_message,
            "data": data,
            "latency": latency,
            "model_reported": model_reported,
            "error_context": error_context,
            "should_try_next_model": True,
        }
