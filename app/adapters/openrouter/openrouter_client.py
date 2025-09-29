from __future__ import annotations

import asyncio
import logging
import os
import time
import weakref
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from importlib.util import find_spec
from threading import Lock
from typing import Any

import httpx

from app.adapters.openrouter.error_handler import ErrorHandler
from app.adapters.openrouter.exceptions import (
    ClientError,
    ConfigurationError,
    NetworkError,
    ValidationError,
)
from app.adapters.openrouter.model_capabilities import ModelCapabilities
from app.adapters.openrouter.payload_logger import PayloadLogger
from app.adapters.openrouter.request_builder import RequestBuilder
from app.adapters.openrouter.response_processor import ResponseProcessor
from app.models.llm.llm_models import ChatRequest, LLMCallResult

logger = logging.getLogger(__name__)


HTTP2_AVAILABLE = find_spec("h2") is not None

if not HTTP2_AVAILABLE:
    logger.warning(
        "HTTP/2 support disabled because the 'h2' package is not installed; falling back to HTTP/1.1"
    )


class OpenRouterClient:
    """Enhanced OpenRouter Chat Completions client with structured output support."""

    # Class-level client pool for connection reuse
    _client_pool: dict[str, httpx.AsyncClient] = {}
    _client_pool_lock = Lock()
    _cleanup_registry: weakref.WeakSet[OpenRouterClient] = weakref.WeakSet()

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
        # Performance settings
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        keepalive_expiry: float = 30.0,
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
        self._timeout = httpx.Timeout(timeout_sec, connect=10.0, read=timeout_sec)
        self._base_url = "https://openrouter.ai/api/v1"
        self._enable_structured_outputs = enable_structured_outputs
        self._closed = False

        # Optional pricing overrides (USD per 1k tokens) for local cost estimation
        try:
            self._price_input_per_1k = float(os.getenv("OPENROUTER_PRICE_INPUT_PER_1K", ""))
        except Exception:
            self._price_input_per_1k = None
        try:
            self._price_output_per_1k = float(os.getenv("OPENROUTER_PRICE_OUTPUT_PER_1K", ""))
        except Exception:
            self._price_output_per_1k = None

        # Performance configuration
        self._limits = httpx.Limits(
            max_keepalive_connections=max_keepalive_connections,
            max_connections=max_connections,
            keepalive_expiry=keepalive_expiry,
        )

        # Initialize components with specific error handling
        try:
            self.request_builder = RequestBuilder(
                api_key=api_key,
                http_referer=http_referer,
                x_title=x_title,
                provider_order=provider_order,
                enable_structured_outputs=enable_structured_outputs,
                structured_output_mode=structured_output_mode,
                require_parameters=require_parameters,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize request builder: {e}",
                context={"component": "request_builder", "original_error": str(e)},
            ) from e

        try:
            self.response_processor = ResponseProcessor(
                enable_stats=enable_stats,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize response processor: {e}",
                context={"component": "response_processor", "original_error": str(e)},
            ) from e

        try:
            self.model_capabilities = ModelCapabilities(
                api_key=api_key,
                base_url=self._base_url,
                http_referer=http_referer,
                x_title=x_title,
                timeout=int(timeout_sec),
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize model capabilities: {e}",
                context={"component": "model_capabilities", "original_error": str(e)},
            ) from e

        try:
            self.error_handler = ErrorHandler(
                max_retries=max_retries,
                backoff_base=backoff_base,
                audit=audit,
                auto_fallback_structured=auto_fallback_structured,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize error handler: {e}",
                context={"component": "error_handler", "original_error": str(e)},
            ) from e

        try:
            self.payload_logger = PayloadLogger(
                debug_payloads=debug_payloads,
                log_truncate_length=log_truncate_length,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize payload logger: {e}",
                context={"component": "payload_logger", "original_error": str(e)},
            ) from e

        # Client management
        self._client_key = f"{self._base_url}:{hash((api_key, timeout_sec, max_connections))}"
        self._client: httpx.AsyncClient | None = None

        # Register for cleanup
        self._cleanup_registry.add(self)

    @classmethod
    async def cleanup_all_clients(cls) -> None:
        """Clean up all shared HTTP clients."""
        with cls._client_pool_lock:
            clients = list(cls._client_pool.values())
            cls._client_pool.clear()

        # Close all clients concurrently
        if clients:
            await asyncio.gather(*[client.aclose() for client in clients], return_exceptions=True)

    async def __aenter__(self) -> OpenRouterClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._closed:
            return

        self._closed = True

        # Don't close shared clients, just remove our reference
        if self._client is not None:
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily construct or reuse a pooled AsyncClient instance."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        # Check if we already have a client reference
        if self._client is not None:
            return self._client

        # Use shared client pool for better connection reuse
        with self._client_pool_lock:
            client = self._client_pool.get(self._client_key)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    limits=self._limits,
                    # Additional performance settings
                    http2=HTTP2_AVAILABLE,
                    follow_redirects=True,
                )
                self._client_pool[self._client_key] = client

            self._client = client
            return client

    def _get_error_message(self, status_code: int, data: dict[str, Any] | None) -> str:
        """Return a human-friendly error message for an HTTP status.

        This mirrors the expectations asserted in tests by mapping common
        statuses to stable, descriptive messages and appending any message
        provided by the API payload when present.
        """
        # Extract optional message from payload (string or nested {error: {message}})
        payload_message: str | None = None
        if data:
            try:
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message")
                    if isinstance(msg, str) and msg:
                        payload_message = msg
                elif isinstance(err, str) and err:
                    payload_message = err
            except (AttributeError, TypeError):
                # Handle malformed data gracefully
                pass

        base_map: dict[int, str] = {
            400: "Invalid or missing request parameters",
            401: "Authentication failed",
            402: "Insufficient account balance",
            404: "Requested resource not found",
            429: "Rate limit exceeded",
        }

        if status_code == 500:
            base = "Internal server error"
        elif status_code >= 500:
            base = f"HTTP {status_code} error"
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
        """Validate initialization parameters with specific error types."""
        # Security: Validate API key presence
        if not api_key or not isinstance(api_key, str):
            raise ConfigurationError(
                "API key is required and must be a non-empty string",
                context={"parameter": "api_key", "type": type(api_key).__name__},
            )
        if len(api_key.strip()) < 10:  # Basic sanity check
            raise ConfigurationError(
                "API key appears to be invalid (too short)",
                context={"parameter": "api_key", "length": len(api_key.strip())},
            )

        # Security: Validate model
        if not model or not isinstance(model, str):
            raise ConfigurationError(
                "Model is required and must be a non-empty string",
                context={"parameter": "model", "type": type(model).__name__},
            )
        if len(model) > 100:
            raise ConfigurationError(
                f"Model name too long (max 100 characters, got {len(model)})",
                context={"parameter": "model", "length": len(model)},
            )

        # Security: Validate headers
        if http_referer and (not isinstance(http_referer, str) or len(http_referer) > 500):
            raise ConfigurationError(
                f"HTTP referer must be a string with max 500 characters (got {len(http_referer)})",
                context={
                    "parameter": "http_referer",
                    "length": len(http_referer) if http_referer else 0,
                },
            )
        if x_title and (not isinstance(x_title, str) or len(x_title) > 200):
            raise ConfigurationError(
                f"X-Title must be a string with max 200 characters (got {len(x_title)})",
                context={"parameter": "x_title", "length": len(x_title) if x_title else 0},
            )

        # Security: Validate timeout
        if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
            raise ConfigurationError(
                f"Timeout must be a positive number (got {timeout_sec})",
                context={
                    "parameter": "timeout_sec",
                    "value": timeout_sec,
                    "type": type(timeout_sec).__name__,
                },
            )
        if timeout_sec > 300:  # 5 minutes max
            raise ConfigurationError(
                f"Timeout too large (max 300 seconds, got {timeout_sec})",
                context={"parameter": "timeout_sec", "value": timeout_sec},
            )

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ConfigurationError(
                f"Max retries must be an integer between 0 and 10 (got {max_retries})",
                context={
                    "parameter": "max_retries",
                    "value": max_retries,
                    "type": type(max_retries).__name__,
                },
            )
        if not isinstance(backoff_base, int | float) or backoff_base < 0:
            raise ConfigurationError(
                f"Backoff base must be a non-negative number (got {backoff_base})",
                context={
                    "parameter": "backoff_base",
                    "value": backoff_base,
                    "type": type(backoff_base).__name__,
                },
            )

        # Validate structured output settings
        if structured_output_mode not in {"json_schema", "json_object"}:
            raise ConfigurationError(
                f"Structured output mode must be 'json_schema' or 'json_object' (got '{structured_output_mode}')",
                context={"parameter": "structured_output_mode", "value": structured_output_mode},
            )

    def _validate_fallback_models(
        self, fallback_models: list[str] | tuple[str, ...] | None
    ) -> list[str]:
        """Validate and return fallback models."""
        validated_fallbacks = []
        if fallback_models:
            for fallback in fallback_models:
                if isinstance(fallback, str) and fallback.strip() and len(fallback) <= 100:
                    validated_fallbacks.append(fallback.strip())
        return validated_fallbacks

    @asynccontextmanager
    async def _request_context(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Context manager for request handling with proper error handling."""
        if self._closed:
            raise ClientError("Cannot use client after it has been closed")

        client = self._ensure_client()

        try:
            yield client
        except httpx.TimeoutException as e:
            raise NetworkError(
                f"Request timeout: {e}",
                context={
                    "client": "shared" if client in self._client_pool.values() else "dedicated",
                    "timeout_seconds": self._timeout.read_timeout
                    if hasattr(self._timeout, "read_timeout")
                    else "unknown",
                },
            ) from e
        except httpx.ConnectError as e:
            raise NetworkError(
                f"Connection failed: {e}",
                context={
                    "client": "shared" if client in self._client_pool.values() else "dedicated",
                    "base_url": self._base_url,
                },
            ) from e
        except httpx.HTTPStatusError:
            # Don't wrap HTTP errors here - let them be handled by the caller
            # This preserves the original httpx.HTTPStatusError for proper handling
            raise
        except Exception as e:
            raise ClientError(
                f"Unexpected client error: {e}",
                context={
                    "client": "shared" if client in self._client_pool.values() else "dedicated",
                    "error_type": type(e).__name__,
                },
            ) from e

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
        if self._closed:
            raise RuntimeError("Client has been closed")

        # Early validation to fail fast
        if not messages:
            raise ValidationError("Messages cannot be empty", context={"messages_count": 0})

        if not isinstance(messages, list):
            raise ValidationError(
                f"Messages must be a list, got {type(messages).__name__}",
                context={"messages_type": type(messages).__name__},
            )

        # Create and validate request with specific error handling
        try:
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
        except Exception as e:
            raise ValidationError(
                f"Invalid chat request parameters: {e}",
                context={"original_error": str(e), "messages_count": len(messages)},
            ) from e

        # Pre-process and validate with specific error handling
        try:
            self.request_builder.validate_chat_request(request)
            sanitized_messages = self.request_builder.sanitize_messages(messages)
        except Exception as e:
            raise ValidationError(
                f"Request validation failed: {e}",
                context={"original_error": str(e), "messages_count": len(messages)},
            ) from e

        # Calculate message metrics
        message_lengths = [len(str(msg.get("content", ""))) for msg in sanitized_messages]
        message_roles = [msg.get("role", "?") for msg in sanitized_messages]
        total_chars = sum(message_lengths)

        # Determine models to try
        primary_model = model_override if model_override else self._model
        models_to_try = self.model_capabilities.build_model_fallback_list(
            primary_model, self._fallback_models, response_format, self._enable_structured_outputs
        )

        if not models_to_try:
            raise ValueError("No models available to try")

        # State tracking
        builder_rf_mode_original = self.request_builder._structured_output_mode
        response_format_initial = response_format if isinstance(response_format, dict) else None

        # Initialize state variables
        last_error_text = None
        last_data = None
        last_latency = None
        last_model_reported = None
        last_response_text = None
        structured_output_used = False
        structured_output_mode_used = None
        structured_parse_error = False
        last_error_context: dict[str, Any] | None = None

        try:
            async with self._request_context() as client:
                # Try each model
                for model_idx, model in enumerate(models_to_try):
                    # Skip models that don't support structured outputs if required
                    if response_format and self._enable_structured_outputs:
                        try:
                            await self.model_capabilities.ensure_structured_supported_models()
                            if not self.model_capabilities.supports_structured_outputs(model):
                                if model == primary_model:
                                    self.error_handler.log_skip_model(
                                        model, "no_structured_outputs_primary", request_id
                                    )
                                    structured_output_used = False
                                    structured_output_mode_used = None
                                else:
                                    self.error_handler.log_skip_model(
                                        model, "no_structured_outputs", request_id
                                    )
                                    continue
                        except Exception as e:
                            # Log but continue with assumption that model supports it
                            logger.warning("Failed to check model capabilities: %s", e)

                    # Determine response format mode for this model
                    rf_mode_current = builder_rf_mode_original
                    response_format_current = response_format_initial

                    # Retry logic for each model
                    for attempt in range(self.error_handler._max_retries + 1):
                        try:
                            result = await self._attempt_request(
                                client=client,
                                model=model,
                                attempt=attempt,
                                sanitized_messages=sanitized_messages,
                                request=request,
                                rf_mode_current=rf_mode_current,
                                response_format_current=response_format_current,
                                message_lengths=message_lengths,
                                message_roles=message_roles,
                                total_chars=total_chars,
                                request_id=request_id,
                            )

                            # Handle successful result
                            if result.get("success"):
                                self.request_builder._structured_output_mode = (
                                    builder_rf_mode_original
                                )
                                return result["llm_result"]

                            # Handle retry/fallback logic
                            if result.get("should_retry"):
                                rf_mode_current = result.get("new_rf_mode", rf_mode_current)
                                response_format_current = result.get(
                                    "new_response_format", response_format_current
                                )
                                structured_output_used = result.get(
                                    "structured_output_used", structured_output_used
                                )
                                structured_output_mode_used = result.get(
                                    "structured_output_mode_used", structured_output_mode_used
                                )

                                # Apply backoff
                                if result.get("backoff_needed"):
                                    await self.error_handler.sleep_backoff(attempt)
                                continue

                            # Update state for potential fallback
                            last_error_text = result.get("error_text")
                            last_data = result.get("data")
                            last_latency = result.get("latency")
                            last_model_reported = result.get("model_reported")
                            last_response_text = result.get("response_text")
                            last_error_context = result.get("error_context")
                            structured_parse_error = result.get("structured_parse_error", False)

                            if result.get("should_try_next_model"):
                                break  # Try next model

                            # Return error result
                            if result.get("error_result"):
                                self.request_builder._structured_output_mode = (
                                    builder_rf_mode_original
                                )
                                return result["error_result"]

                        except httpx.TimeoutException as e:
                            # Handle timeout specifically
                            last_error_text = f"Request timeout: {str(e)}"
                            last_error_context = {
                                "status_code": None,
                                "message": "Request timeout",
                                "api_error": str(e),
                            }
                            # Timeout should be retried if within retry limits
                            if attempt < self.error_handler._max_retries:
                                await self.error_handler.sleep_backoff(attempt)
                                continue
                            else:
                                break  # Try next model
                        except httpx.ConnectError as e:
                            # Handle connection errors specifically
                            last_error_text = f"Connection error: {str(e)}"
                            last_error_context = {
                                "status_code": None,
                                "message": "Connection failed",
                                "api_error": str(e),
                            }
                            # Connection errors should be retried if within retry limits
                            if attempt < self.error_handler._max_retries:
                                await self.error_handler.sleep_backoff(attempt)
                                continue
                            else:
                                break  # Try next model
                        except httpx.HTTPStatusError as e:
                            # Handle HTTP status errors specifically
                            last_error_text = f"HTTP {e.response.status_code} error: {str(e)}"
                            last_error_context = {
                                "status_code": e.response.status_code,
                                "message": "HTTP status error",
                                "api_error": str(e),
                            }
                            # HTTP errors should be retried if within retry limits
                            if attempt < self.error_handler._max_retries:
                                await self.error_handler.sleep_backoff(attempt)
                                continue
                            else:
                                break  # Try next model
                        except Exception as e:
                            # Handle other unexpected exceptions
                            last_error_text = f"Unexpected error: {str(e)}"
                            last_error_context = {
                                "status_code": None,
                                "message": "Client exception",
                                "api_error": str(e),
                            }
                            # Generic exceptions should be retried if within retry limits
                            if attempt < self.error_handler._max_retries:
                                await self.error_handler.sleep_backoff(attempt)
                                continue
                            else:
                                break  # Try next model

                    # Break if structured output parse error (don't try other models)
                    if structured_parse_error:
                        break

                    # Log fallback to next model
                    if model_idx < len(models_to_try) - 1:
                        next_model = models_to_try[model_idx + 1]
                        self.error_handler.log_fallback(model, next_model, request_id)

        except Exception as e:
            # Handle context manager or other critical errors
            last_error_text = f"Critical error: {str(e)}"
            last_error_context = {
                "status_code": None,
                "message": "Critical client error",
                "api_error": str(e),
                "error_type": "critical",
            }

        finally:
            # Always restore original mode
            self.request_builder._structured_output_mode = builder_rf_mode_original

        # All models exhausted - build final error result
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
            openrouter_response_text=last_response_text,
            openrouter_response_json=last_data,
            tokens_prompt=None,
            tokens_completion=None,
            cost_usd=None,
            latency_ms=last_latency,
            error_text=(
                "structured_output_parse_error"
                if structured_parse_error
                else (last_error_text or "All retries and fallbacks exhausted")
            ),
            request_headers=redacted_headers,
            request_messages=sanitized_messages,
            endpoint="/api/v1/chat/completions",
            structured_output_used=structured_output_used,
            structured_output_mode=structured_output_mode_used,
            error_context=last_error_context,
        )

    async def _attempt_request(
        self,
        client: httpx.AsyncClient,
        model: str,
        attempt: int,
        sanitized_messages: list[dict[str, str]],
        request: ChatRequest,
        rf_mode_current: str,
        response_format_current: dict[str, Any] | None,
        message_lengths: list[int],
        message_roles: list[str],
        total_chars: int,
        request_id: int | None,
    ) -> dict[str, Any]:
        """Attempt a single request with comprehensive error handling."""

        self.error_handler.log_attempt(attempt, model, request_id)

        # Build request components
        self.request_builder._structured_output_mode = rf_mode_current
        headers = self.request_builder.build_headers()
        body = self.request_builder.build_request_body(
            model, sanitized_messages, request, response_format_current
        )

        if rf_mode_current == "json_object" and "response_format" in body:
            body["response_format"] = {"type": "json_object"}

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
        structured_output_used = rf_included
        structured_output_mode_used = rf_mode_current if rf_included else None

        # Make request with timeout and error handling
        started = time.perf_counter()
        try:
            self.payload_logger.log_request(
                model=model,
                attempt=attempt,
                request_id=request_id,
                message_lengths=message_lengths,
                message_roles=message_roles,
                total_chars=total_chars,
                structured_output=rf_included,
                rf_mode=rf_mode_current,
                transforms=body.get("transforms"),
            )

            if self.payload_logger._debug_payloads:
                self.payload_logger.log_request_payload(
                    headers, body, sanitized_messages, rf_mode_current
                )

            resp = await client.post(
                "/chat/completions",  # Use relative URL since base_url is set
                headers=headers,
                json=body,
            )

            latency = int((time.perf_counter() - started) * 1000)

            # Parse response with error handling
            try:
                data = resp.json()
            except Exception as e:
                return {
                    "success": False,
                    "error_text": f"Failed to parse JSON response: {e}",
                    "latency": latency,
                    "should_try_next_model": True,
                }

            if self.payload_logger._debug_payloads:
                self.payload_logger.log_response_payload(data)

            status_code = resp.status_code
            model_reported = data.get("model", model) if isinstance(data, dict) else model

            # Handle successful response (200)
            if status_code == 200:
                return await self._handle_successful_response(
                    data=data,
                    rf_included=rf_included,
                    rf_mode_current=rf_mode_current,
                    response_format_current=response_format_current,
                    model=model,
                    model_reported=model_reported,
                    latency=latency,
                    attempt=attempt,
                    request_id=request_id,
                    structured_output_used=structured_output_used,
                    structured_output_mode_used=structured_output_mode_used,
                    headers=headers,
                    sanitized_messages=sanitized_messages,
                )

            # Handle error responses
            return await self._handle_error_response(
                status_code=status_code,
                data=data,
                resp=resp,
                rf_included=rf_included,
                rf_mode_current=rf_mode_current,
                response_format_current=response_format_current,
                model=model,
                model_reported=model_reported,
                latency=latency,
                attempt=attempt,
                request_id=request_id,
                headers=headers,
                sanitized_messages=sanitized_messages,
            )

        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "success": False,
                "error_text": "Request timeout",
                "latency": latency,
                "should_retry": attempt < self.error_handler._max_retries,
                "backoff_needed": True,
            }
        except Exception as e:
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "success": False,
                "error_text": str(e),
                "latency": latency,
                "should_retry": attempt < self.error_handler._max_retries,
                "backoff_needed": True,
            }

    async def _handle_successful_response(
        self,
        data: dict[str, Any],
        rf_included: bool,
        rf_mode_current: str,
        response_format_current: dict[str, Any] | None,
        model: str,
        model_reported: str,
        latency: int,
        attempt: int,
        request_id: int | None,
        structured_output_used: bool,
        structured_output_mode_used: str | None,
        headers: dict[str, str],
        sanitized_messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Handle successful API response."""

        # Extract response data
        text, usage, cost_usd = self.response_processor.extract_response_data(data, rf_included)

        # Check for truncation
        truncated, truncated_finish, truncated_native = (
            self.response_processor.is_completion_truncated(data)
        )

        if truncated:
            self.error_handler.log_truncated_completion(
                model, truncated_finish, truncated_native, request_id
            )

            # Handle truncation with structured output downgrade
            if rf_included and response_format_current:
                if rf_mode_current == "json_schema":
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": "json_object",
                        "new_response_format": {"type": "json_object"},
                        "backoff_needed": True,
                        "structured_output_used": True,
                        "structured_output_mode_used": "json_object",
                    }
                elif rf_mode_current == "json_object":
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": rf_mode_current,
                        "new_response_format": None,
                        "backoff_needed": True,
                        "structured_output_used": False,
                        "structured_output_mode_used": None,
                    }

            if attempt < self.error_handler._max_retries:
                return {
                    "success": False,
                    "should_retry": True,
                    "backoff_needed": True,
                }

            # Handle truncation - be more permissive with GPT-5
            model_lower = model.lower()

            # GPT-5 specific handling: try multiple strategies before falling back
            if "gpt-5" in model_lower:
                # For GPT-5, first try with reduced temperature to see if it helps
                if attempt == 0 and truncated:
                    logger.info(
                        "gpt5_truncation_attempt_1",
                        extra={
                            "model": model,
                            "attempt": attempt,
                            "finish_reason": truncated_finish,
                        },
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "backoff_needed": True,
                    }
                # Second attempt: try with even lower temperature and higher max_tokens
                elif attempt == 1 and truncated:
                    logger.info(
                        "gpt5_truncation_attempt_2",
                        extra={
                            "model": model,
                            "attempt": attempt,
                            "finish_reason": truncated_finish,
                        },
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "backoff_needed": True,
                    }
                # Only fallback to next model as last resort
                elif attempt >= 2 and truncated:
                    logger.warning(
                        "gpt5_fallback_to_next_model",
                        extra={
                            "model": model,
                            "attempt": attempt,
                            "finish_reason": truncated_finish,
                        },
                    )
                    return {
                        "success": False,
                        "error_text": "completion_truncated_gpt5",
                        "response_text": text if isinstance(text, str) else None,
                        "should_try_next_model": True,
                    }
            elif attempt < self.error_handler._max_retries:
                # For other models, try again with backoff
                return {
                    "success": False,
                    "should_retry": True,
                    "backoff_needed": True,
                }
            else:
                # Final attempt with truncation
                return {
                    "success": False,
                    "error_text": "completion_truncated",
                    "response_text": text if isinstance(text, str) else None,
                    "should_try_next_model": True,
                }

        # Validate structured output if expected
        if rf_included and response_format_current:
            is_valid, processed_text = self.response_processor.validate_structured_response(
                text, rf_included, response_format_current
            )
            if not is_valid:
                # Try fallback for invalid JSON
                if rf_mode_current == "json_schema" and attempt < self.error_handler._max_retries:
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": "json_object",
                        "new_response_format": {"type": "json_object"},
                        "backoff_needed": True,
                    }

                # Treat as structured output parse error
                return {
                    "success": False,
                    "error_text": "structured_output_parse_error",
                    "response_text": processed_text or None,
                    "structured_parse_error": True,
                    "should_try_next_model": False,  # Don't try other models for parse errors
                }
            else:
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

        # If API did not provide cost, optionally estimate using env-provided rates
        if cost_usd is None and tokens_prompt is not None and tokens_completion is not None:
            if self._price_input_per_1k is not None and self._price_output_per_1k is not None:
                try:
                    cost_usd = (float(tokens_prompt) / 1000.0) * self._price_input_per_1k + (
                        float(tokens_completion) / 1000.0
                    ) * self._price_output_per_1k
                except Exception:
                    cost_usd = None

        # Log successful response
        self.payload_logger.log_response(
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
            rf_mode=rf_mode_current,
        )

        self.error_handler.log_success(
            attempt,
            model,
            200,
            latency,
            structured_output_used,
            structured_output_mode_used,
            request_id,
        )

        # Prepare redacted headers
        redacted_headers = self.request_builder.get_redacted_headers(headers)

        # Return successful result
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
            ),
        }

    async def _handle_error_response(
        self,
        status_code: int,
        data: dict[str, Any],
        resp: httpx.Response,
        rf_included: bool,
        rf_mode_current: str,
        response_format_current: dict[str, Any] | None,
        model: str,
        model_reported: str,
        latency: int,
        attempt: int,
        request_id: int | None,
        headers: dict[str, str],
        sanitized_messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Handle error responses with appropriate retry/fallback logic."""

        # Handle response format errors with graceful degradation
        if self.response_processor.should_downgrade_response_format(status_code, data, rf_included):
            should_downgrade, new_mode = self.error_handler.should_downgrade_response_format(
                status_code, data, rf_mode_current, rf_included, attempt
            )
            if should_downgrade:
                if new_mode:
                    self.error_handler.log_response_format_downgrade(
                        model,
                        "json_schema",
                        new_mode,
                        request_id,
                    )
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": new_mode,
                        "new_response_format": {"type": "json_object"}
                        if new_mode == "json_object"
                        else None,
                        "backoff_needed": True,
                    }
                else:
                    self.error_handler.log_structured_outputs_disabled(model, request_id)
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": rf_mode_current,
                        "new_response_format": None,
                        "structured_output_used": False,
                        "structured_output_mode_used": None,
                        "backoff_needed": True,
                    }

        # Extract response content and error context
        text, usage, cost_usd = self.response_processor.extract_response_data(data, rf_included)
        error_context = self.response_processor.get_error_context(status_code, data)
        error_message = error_context["message"]

        # Prepare redacted headers
        redacted_headers = self.request_builder.get_redacted_headers(headers)

        # Non-retryable errors
        if self.error_handler.is_non_retryable_error(status_code):
            self.error_handler.log_error(attempt, model, status_code, error_message, request_id)
            return {
                "success": False,
                "error_result": self.error_handler.build_error_result(
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

        # 404: Try next model if available
        if self.error_handler.should_try_next_model(status_code):
            # Handle structured output parameter errors
            api_error_lower = (
                str(error_context.get("api_error", "")).lower()
                if isinstance(error_context, dict)
                else ""
            )

            if (
                rf_included
                and response_format_current
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
                if rf_mode_current == "json_schema":
                    self.error_handler.log_response_format_downgrade(
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
                elif rf_mode_current == "json_object":
                    self.error_handler.log_structured_outputs_disabled(model, request_id)
                    return {
                        "success": False,
                        "should_retry": True,
                        "new_rf_mode": rf_mode_current,
                        "new_response_format": None,
                        "structured_output_used": False,
                        "structured_output_mode_used": None,
                        "backoff_needed": True,
                    }

            # Log and try next model
            self.error_handler.log_error(
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

        # Retryable errors
        if self.error_handler.should_retry(status_code, attempt):
            if status_code == 429:
                await self.error_handler.handle_rate_limit(resp.headers)
            return {
                "success": False,
                "should_retry": True,
                "backoff_needed": status_code != 429,  # Rate limit handling already done
                "error_text": error_message,
                "error_context": error_context,
            }

        # Unknown/unhandled error - try next model
        self.error_handler.log_error(attempt, model, status_code, error_message, request_id)
        return {
            "success": False,
            "error_text": error_message,
            "data": data,
            "latency": latency,
            "model_reported": model_reported,
            "error_context": error_context,
            "should_try_next_model": True,
        }

    async def get_models(self) -> dict[str, Any]:
        """Get available models from OpenRouter API."""
        if self._closed:
            raise RuntimeError("Client has been closed")
        return await self.model_capabilities.get_models()

    async def get_structured_models(self) -> set[str]:
        """Get set of models that support structured outputs."""
        if self._closed:
            raise RuntimeError("Client has been closed")
        return await self.model_capabilities.get_structured_models()


# Utility function for backoff (kept for compatibility)
async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Exponential backoff with light jitter."""
    import asyncio
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
