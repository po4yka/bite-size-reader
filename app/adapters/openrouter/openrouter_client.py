from __future__ import annotations

import asyncio
import logging
import os
import threading
import weakref
from contextlib import asynccontextmanager
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from typing import Self

    from app.models.llm.llm_models import ChatRequest, LLMCallResult
    from app.utils.circuit_breaker import CircuitBreaker

import httpx

from app.adapters.openrouter import chat_completions, client_validation
from app.adapters.openrouter.error_handler import ErrorHandler
from app.adapters.openrouter.exceptions import (
    ClientError,
    ConfigurationError,
    NetworkError,
)
from app.adapters.openrouter.model_capabilities import ModelCapabilities
from app.adapters.openrouter.payload_logger import PayloadLogger
from app.adapters.openrouter.request_builder import RequestBuilder
from app.adapters.openrouter.response_processor import ResponseProcessor
from app.core.async_utils import raise_if_cancelled

logger = logging.getLogger(__name__)


HTTP2_AVAILABLE = find_spec("h2") is not None

if not HTTP2_AVAILABLE:
    logger.warning(
        "HTTP/2 support disabled because the 'h2' package is not installed; falling back to HTTP/1.1"
    )


class OpenRouterClient:
    """Enhanced OpenRouter Chat Completions client with structured output support.

    This client implements the LLMClientProtocol interface, allowing it to be used
    interchangeably with other LLM providers (OpenAI, Anthropic) in the application.
    """

    # Provider name for protocol compliance
    _provider_name: str = "openrouter"

    # Class-level client pool for connection reuse
    _client_pools: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[str, httpx.AsyncClient]
    ] = weakref.WeakKeyDictionary()
    _cleanup_registry: weakref.WeakSet[OpenRouterClient] = weakref.WeakSet()

    # Async lock for client pool access (created lazily per event loop)
    _client_pool_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
        weakref.WeakKeyDictionary()
    )
    # Thread lock to protect async lock initialization (fixes race condition)
    _lock_init_lock = threading.Lock()

    @classmethod
    def _get_event_loop(cls) -> asyncio.AbstractEventLoop:
        """Return the running event loop.

        Raises RuntimeError if called outside an async context -- this is
        intentional, as the client pool must only be accessed from async code.
        """
        return asyncio.get_running_loop()

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Get or create the async lock for client pool access.

        Thread-safe initialization using double-checked locking pattern.
        Prevents race condition where multiple threads could create different locks.
        """
        loop = cls._get_event_loop()

        # Fast path: lock already exists (no thread lock needed for read)
        lock = cls._client_pool_locks.get(loop)
        if lock is not None:
            return lock

        # Slow path: create the lock with thread-safe initialization
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
        # Response size limits
        max_response_size_mb: int = 10,
        # Circuit breaker for fault tolerance
        circuit_breaker: CircuitBreaker | None = None,
        # Prompt caching settings
        enable_prompt_caching: bool = True,
        prompt_cache_ttl: str = "ephemeral",
        cache_system_prompt: bool = True,
        cache_large_content_threshold: int = 4096,
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
            max_response_size_mb,
        )

        # Store configuration
        self._api_key = api_key
        self._model = model
        self._fallback_models = self._validate_fallback_models(fallback_models)
        self._timeout = httpx.Timeout(timeout_sec, connect=10.0, read=timeout_sec)
        self._base_url = "https://openrouter.ai/api/v1"
        self._enable_structured_outputs = enable_structured_outputs
        self._closed = False
        self._max_response_size_bytes = int(max_response_size_mb) * 1024 * 1024
        # Store prompt caching settings
        self._enable_prompt_caching = enable_prompt_caching
        self._prompt_cache_ttl = prompt_cache_ttl
        self._cache_system_prompt = cache_system_prompt
        self._cache_large_content_threshold = cache_large_content_threshold

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
                # Prompt caching settings
                enable_prompt_caching=enable_prompt_caching,
                prompt_cache_ttl=prompt_cache_ttl,
                cache_system_prompt=cache_system_prompt,
                cache_large_content_threshold=cache_large_content_threshold,
            )
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Failed to initialize request builder: {e}"
            raise ConfigurationError(
                msg,
                context={"component": "request_builder", "original_error": str(e)},
            ) from e

        try:
            self.response_processor = ResponseProcessor(
                enable_stats=enable_stats,
            )
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Failed to initialize response processor: {e}"
            raise ConfigurationError(
                msg,
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
            raise_if_cancelled(e)
            msg = f"Failed to initialize model capabilities: {e}"
            raise ConfigurationError(
                msg,
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
            raise_if_cancelled(e)
            msg = f"Failed to initialize error handler: {e}"
            raise ConfigurationError(
                msg,
                context={"component": "error_handler", "original_error": str(e)},
            ) from e

        try:
            self.payload_logger = PayloadLogger(
                debug_payloads=debug_payloads,
                log_truncate_length=log_truncate_length,
            )
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Failed to initialize payload logger: {e}"
            raise ConfigurationError(
                msg,
                context={"component": "payload_logger", "original_error": str(e)},
            ) from e

        # Client management
        self._client_key = f"{self._base_url}:{hash((api_key, timeout_sec, max_connections))}"
        self._client: httpx.AsyncClient | None = None
        self._circuit_breaker = circuit_breaker

        # Register for cleanup
        self._cleanup_registry.add(self)

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Return the circuit breaker instance if configured."""
        return self._circuit_breaker

    def get_circuit_breaker_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        if self._circuit_breaker:
            return self._circuit_breaker.get_stats()
        return {"state": "disabled"}

    @property
    def provider_name(self) -> str:
        """Return the provider name for LLMClientProtocol compliance."""
        return self._provider_name

    @classmethod
    async def cleanup_all_clients(cls) -> None:
        """Clean up all shared HTTP clients."""
        with cls._lock_init_lock:
            pools = list(cls._client_pools.values())
            cls._client_pools = weakref.WeakKeyDictionary()
            cls._client_pool_locks = weakref.WeakKeyDictionary()

        clients = [client for pool in pools for client in pool.values()]

        # Close all clients concurrently
        if clients:
            await asyncio.gather(*[client.aclose() for client in clients], return_exceptions=True)

    async def __aenter__(self) -> Self:
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

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily construct or reuse a pooled AsyncClient instance."""
        if self._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)

        # Check if we already have a client reference
        if self._client is not None:
            return self._client

        # Use shared client pool for better connection reuse
        async with self._get_pool_lock():
            pool = self._get_pool()
            client = pool.get(self._client_key)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    limits=self._limits,
                    # Additional performance settings
                    http2=HTTP2_AVAILABLE,
                    follow_redirects=True,
                )
                pool[self._client_key] = client

            self._client = client
            return client

    def _get_error_message(self, status_code: int, data: dict[str, Any] | None) -> str:
        return client_validation.get_error_message(status_code, data)

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
        max_response_size_mb: int,
    ) -> None:
        client_validation.validate_init_params(
            api_key=api_key,
            model=model,
            fallback_models=fallback_models,
            http_referer=http_referer,
            x_title=x_title,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            backoff_base=backoff_base,
            structured_output_mode=structured_output_mode,
            max_response_size_mb=max_response_size_mb,
        )

    def _validate_fallback_models(
        self, fallback_models: list[str] | tuple[str, ...] | None
    ) -> list[str]:
        return client_validation.validate_fallback_models(fallback_models)

    @asynccontextmanager
    async def _request_context(self) -> AsyncGenerator[httpx.AsyncClient]:  # type: ignore[type-arg, unused-ignore]
        """Context manager for request handling with proper error handling."""
        if self._closed:
            msg = "Cannot use client after it has been closed"
            raise ClientError(msg)

        client = await self._ensure_client()

        try:
            yield client
        except httpx.TimeoutException as e:
            msg = f"Request timeout: {e}"
            raise NetworkError(
                msg,
                context={
                    "client": "shared" if client in self._get_pool().values() else "dedicated",
                    "timeout_seconds": (
                        self._timeout.read_timeout
                        if hasattr(self._timeout, "read_timeout")
                        else "unknown"
                    ),
                },
            ) from e
        except httpx.ConnectError as e:
            msg = f"Connection failed: {e}"
            raise NetworkError(
                msg,
                context={
                    "client": "shared" if client in self._get_pool().values() else "dedicated",
                    "base_url": self._base_url,
                },
            ) from e
        except httpx.HTTPStatusError:
            # Don't wrap HTTP errors here - let them be handled by the caller
            # This preserves the original httpx.HTTPStatusError for proper handling
            raise
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Unexpected client error: {e}"
            raise ClientError(
                msg,
                context={
                    "client": "shared" if client in self._get_pool().values() else "dedicated",
                    "error_type": type(e).__name__,
                },
            ) from e

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
        fallback_models_override: tuple[str, ...] | list[str] | None = None,
    ) -> LLMCallResult:
        return await chat_completions.chat(
            self,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            request_id=request_id,
            response_format=response_format,
            model_override=model_override,
            fallback_models_override=fallback_models_override,
        )

    async def _attempt_request(
        self,
        client: httpx.AsyncClient,
        model: str,
        attempt: int,
        sanitized_messages: list[dict[str, Any]],
        request: ChatRequest,
        rf_mode_current: str,
        response_format_current: dict[str, Any] | None,
        message_lengths: list[int],
        message_roles: list[str],
        total_chars: int,
        request_id: int | None,
    ) -> dict[str, Any]:
        return await chat_completions._attempt_request(
            self,
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
        sanitized_messages: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return await chat_completions._handle_successful_response(
            self,
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
            max_tokens=max_tokens,
        )

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
        sanitized_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await chat_completions._handle_error_response(
            self,
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

    async def get_models(self) -> dict[str, Any]:
        """Get available models from OpenRouter API."""
        if self._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)
        return await self.model_capabilities.get_models()

    async def get_structured_models(self) -> set[str]:
        """Get set of models that support structured outputs."""
        if self._closed:
            msg = "Client has been closed"
            raise RuntimeError(msg)
        return await self.model_capabilities.get_structured_models()


# Utility function for backoff (kept for compatibility)
async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Exponential backoff with light jitter."""
    import asyncio
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
