"""OpenAI LLM client implementation.

This module provides a direct OpenAI API client that implements the LLMClientProtocol.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import weakref
from contextlib import asynccontextmanager
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

import httpx

from app.adapters.llm.openai.request_builder import (
    OpenAIRequestBuilder,
    calculate_cost,
)
from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.models.llm.llm_models import LLMCallResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from app.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

HTTP2_AVAILABLE = find_spec("h2") is not None


class OpenAIClient:
    """OpenAI Chat Completions client implementing LLMClientProtocol.

    This client provides direct access to OpenAI's API with:
    - Structured output support via json_schema
    - Fallback model chain
    - Circuit breaker integration
    - Connection pooling
    """

    _provider_name: str = "openai"

    # Class-level client pool for connection reuse
    _client_pools: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[str, httpx.AsyncClient]
    ] = weakref.WeakKeyDictionary()
    _client_pool_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
        weakref.WeakKeyDictionary()
    )
    _lock_init_lock = threading.Lock()

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o",
        fallback_models: list[str] | tuple[str, ...] | None = None,
        organization: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        debug_payloads: bool = False,
        enable_structured_outputs: bool = True,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        keepalive_expiry: float = 30.0,
        max_response_size_mb: int = 10,
        circuit_breaker: CircuitBreaker | None = None,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Default model to use.
            fallback_models: List of fallback models if primary fails.
            organization: Optional organization ID.
            timeout_sec: Request timeout in seconds.
            max_retries: Maximum retry attempts per model.
            backoff_base: Base delay for exponential backoff.
            debug_payloads: Whether to log request/response payloads.
            enable_structured_outputs: Whether to use structured output mode.
            max_connections: Maximum concurrent connections.
            max_keepalive_connections: Maximum keepalive connections.
            keepalive_expiry: Keepalive connection expiry in seconds.
            max_response_size_mb: Maximum response size in MB.
            circuit_breaker: Optional circuit breaker instance.
            audit: Optional audit callback function.
        """
        self._validate_api_key(api_key)

        self._api_key = api_key
        self._model = model
        self._fallback_models = list(fallback_models) if fallback_models else []
        self._timeout = httpx.Timeout(timeout_sec, connect=10.0, read=timeout_sec)
        self._base_url = "https://api.openai.com/v1"
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._debug_payloads = debug_payloads
        self._enable_structured_outputs = enable_structured_outputs
        self._max_response_size_bytes = int(max_response_size_mb) * 1024 * 1024
        self._circuit_breaker = circuit_breaker
        self._audit = audit
        self._closed = False

        # Connection pool limits
        self._limits = httpx.Limits(
            max_keepalive_connections=max_keepalive_connections,
            max_connections=max_connections,
            keepalive_expiry=keepalive_expiry,
        )

        # Request builder
        self._request_builder = OpenAIRequestBuilder(
            api_key=api_key,
            organization=organization,
            enable_structured_outputs=enable_structured_outputs,
        )

        # Client management
        self._client_key = f"{self._base_url}:{hash((api_key, timeout_sec, max_connections))}"
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _validate_api_key(api_key: str) -> None:
        """Validate API key format."""
        if not api_key or not isinstance(api_key, str):
            msg = "API key is required and must be a non-empty string"
            raise ValueError(msg)
        if len(api_key.strip()) < 10:
            msg = "API key appears to be invalid (too short)"
            raise ValueError(msg)

    @property
    def provider_name(self) -> str:
        """Return the provider name for LLMClientProtocol compliance."""
        return self._provider_name

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Return the circuit breaker instance if configured."""
        return self._circuit_breaker

    @classmethod
    def _get_event_loop(cls) -> asyncio.AbstractEventLoop:
        """Return the current event loop."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Get or create the async lock for client pool access."""
        loop = cls._get_event_loop()
        lock = cls._client_pool_locks.get(loop)
        if lock is not None:
            return lock

        with cls._lock_init_lock:
            lock = cls._client_pool_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                cls._client_pool_locks[loop] = lock
            return lock

    @classmethod
    def _get_pool(cls) -> dict[str, httpx.AsyncClient]:
        """Get or create the client pool for the current event loop."""
        loop = cls._get_event_loop()
        pool = cls._client_pools.get(loop)
        if pool is not None:
            return pool

        with cls._lock_init_lock:
            pool = cls._client_pools.get(loop)
            if pool is None:
                pool = {}
                cls._client_pools[loop] = pool
            return pool

    async def __aenter__(self) -> OpenAIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the client and release resources."""
        if self._closed:
            return
        self._closed = True
        self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily construct or reuse a pooled AsyncClient instance."""
        if self._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)

        if self._client is not None:
            return self._client

        async with self._get_pool_lock():
            pool = self._get_pool()
            client = pool.get(self._client_key)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    limits=self._limits,
                    http2=HTTP2_AVAILABLE,
                    follow_redirects=True,
                )
                pool[self._client_key] = client

            self._client = client
            return client

    @asynccontextmanager
    async def _request_context(self) -> AsyncGenerator[httpx.AsyncClient]:
        """Context manager for request handling."""
        if self._closed:
            msg = "Cannot use client after it has been closed"
            raise RuntimeError(msg)

        client = await self._ensure_client()
        try:
            yield client
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(f"Connection failed: {e}") from e

    async def _sleep_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        import random

        base_delay = max(0.0, self._backoff_base * (2**attempt))
        jitter = 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(base_delay * jitter)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
        request_id: int | None = None,
        response_format: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> LLMCallResult:
        """Send a chat completion request to OpenAI.

        Args:
            messages: List of message dictionaries.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            top_p: Nucleus sampling parameter.
            stream: Whether to stream (not implemented).
            request_id: Optional request ID for tracing.
            response_format: Optional structured output format.
            model_override: Optional model override.

        Returns:
            LLMCallResult with response data.
        """
        if self._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)

        # Check circuit breaker
        if self._circuit_breaker and not self._circuit_breaker.can_proceed():
            logger.warning(
                "openai_circuit_breaker_open",
                extra={"request_id": request_id},
            )
            return LLMCallResult(
                status="error",
                model=None,
                response_text=None,
                error_text="Service temporarily unavailable (circuit breaker open)",
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=0.0,
                latency_ms=0,
            )

        if not messages:
            msg = "Messages cannot be empty"
            raise ValueError(msg)

        # Build model list to try
        primary_model = model_override or self._model
        models_to_try = [primary_model] + [m for m in self._fallback_models if m != primary_model]

        last_error: str | None = None
        last_latency: int | None = None

        async with self._request_context() as client:
            for model in models_to_try:
                for attempt in range(self._max_retries + 1):
                    try:
                        result = await self._attempt_request(
                            client=client,
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            top_p=top_p,
                            response_format=response_format,
                            request_id=request_id,
                            attempt=attempt,
                        )

                        if result.status == "ok":
                            if self._circuit_breaker:
                                self._circuit_breaker.record_success()
                            return result

                        # Check if we should retry
                        if result.error_text and "rate_limit" in result.error_text.lower():
                            if attempt < self._max_retries:
                                await self._sleep_backoff(attempt)
                                continue

                        last_error = result.error_text
                        last_latency = result.latency_ms
                        break  # Try next model

                    except (TimeoutError, ConnectionError) as e:
                        last_error = str(e)
                        if attempt < self._max_retries:
                            await self._sleep_backoff(attempt)
                            continue
                        break  # Try next model

                    except Exception as e:
                        raise_if_cancelled(e)
                        last_error = f"Unexpected error: {e}"
                        break  # Try next model

        # All models exhausted
        if self._circuit_breaker:
            self._circuit_breaker.record_failure()

        return LLMCallResult(
            status="error",
            model=primary_model,
            response_text=None,
            error_text=last_error or "All retries and fallbacks exhausted",
            tokens_prompt=0,
            tokens_completion=0,
            cost_usd=None,
            latency_ms=last_latency,
            endpoint="/v1/chat/completions",
        )

    async def _attempt_request(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None,
        top_p: float | None,
        response_format: dict[str, Any] | None,
        request_id: int | None,
        attempt: int,
    ) -> LLMCallResult:
        """Attempt a single request to OpenAI."""
        headers = self._request_builder.build_headers()
        body = self._request_builder.build_request_body(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            response_format=response_format,
        )

        if self._debug_payloads:
            logger.debug(
                "openai_request",
                extra={
                    "model": model,
                    "attempt": attempt,
                    "request_id": request_id,
                    "message_count": len(messages),
                },
            )

        started = time.perf_counter()

        try:
            resp = await client.post("/chat/completions", headers=headers, json=body)
        except Exception as e:
            raise_if_cancelled(e)
            latency = int((time.perf_counter() - started) * 1000)
            return LLMCallResult(
                status="error",
                model=model,
                response_text=None,
                error_text=f"Request failed: {e}",
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=None,
                latency_ms=latency,
            )

        latency = int((time.perf_counter() - started) * 1000)

        # Validate response size
        try:
            await validate_response_size(resp, self._max_response_size_bytes, "OpenAI")
        except ResponseSizeError as e:
            return LLMCallResult(
                status="error",
                model=model,
                response_text=None,
                error_text=f"Response too large: {e}",
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=None,
                latency_ms=latency,
            )

        # Parse response
        try:
            data = resp.json()
        except Exception as e:
            raise_if_cancelled(e)
            return LLMCallResult(
                status="error",
                model=model,
                response_text=None,
                error_text=f"Failed to parse JSON response: {e}",
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=None,
                latency_ms=latency,
            )

        if self._debug_payloads:
            logger.debug(
                "openai_response", extra={"status": resp.status_code, "latency_ms": latency}
            )

        # Handle error responses
        if resp.status_code != 200:
            error_msg = self._extract_error_message(data)
            return LLMCallResult(
                status="error",
                model=model,
                response_text=None,
                response_json=data,
                error_text=error_msg,
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=None,
                latency_ms=latency,
                error_context={"status_code": resp.status_code, "api_error": error_msg},
            )

        # Extract successful response
        return self._parse_success_response(data, model, latency, headers, messages)

    def _extract_error_message(self, data: dict[str, Any]) -> str:
        """Extract error message from API response."""
        error = data.get("error", {})
        if isinstance(error, dict):
            return error.get("message", "Unknown API error")
        if isinstance(error, str):
            return error
        return "Unknown API error"

    def _parse_success_response(
        self,
        data: dict[str, Any],
        model: str,
        latency: int,
        headers: dict[str, str],
        messages: list[dict[str, Any]],
    ) -> LLMCallResult:
        """Parse a successful API response."""
        choices = data.get("choices", [])
        if not choices:
            return LLMCallResult(
                status="error",
                model=model,
                response_text=None,
                response_json=data,
                error_text="No choices in response",
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=None,
                latency_ms=latency,
            )

        first_choice = choices[0]
        message = first_choice.get("message", {})
        content = message.get("content", "")
        finish_reason = first_choice.get("finish_reason")

        # Check for truncation
        if finish_reason == "length":
            logger.warning("openai_response_truncated", extra={"model": model})

        # Extract usage
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Calculate cost
        model_reported = data.get("model", model)
        cost = calculate_cost(model_reported, prompt_tokens, completion_tokens)

        # Redact headers for storage
        redacted_headers = self._request_builder.get_redacted_headers(headers)
        sanitized_messages = self._request_builder.sanitize_messages(messages)

        return LLMCallResult(
            status="ok",
            model=model_reported,
            response_text=content,
            response_json=data,
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            cost_usd=cost,
            latency_ms=latency,
            request_headers=redacted_headers,
            request_messages=sanitized_messages,
            endpoint="/v1/chat/completions",
            structured_output_used=bool(data.get("response_format")),
        )
