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
    from typing import Self

import httpx

from app.adapters.openrouter.chat_orchestrator import ChatOrchestrator
from app.adapters.openrouter.chat_state import ChatState
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
from app.core.async_utils import raise_if_cancelled
from app.models.llm.llm_models import ChatRequest, LLMCallResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from app.utils.circuit_breaker import CircuitBreaker

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
        """Return the current event loop (running preferred)."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

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

        # Chat orchestrator (owns the model x attempt retry loop)
        self._chat_orchestrator = ChatOrchestrator(
            request_builder=self.request_builder,
            response_processor=self.response_processor,
            error_handler=self.error_handler,
            model_capabilities=self.model_capabilities,
            payload_logger=self.payload_logger,
            circuit_breaker=circuit_breaker,
            max_response_size_bytes=self._max_response_size_bytes,
            price_input_per_1k=self._price_input_per_1k,
            price_output_per_1k=self._price_output_per_1k,
            get_error_message=self._get_error_message,
        )

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
        max_response_size_mb: int,
    ) -> None:
        """Validate initialization parameters with specific error types."""
        # Security: Validate API key presence
        if not api_key or not isinstance(api_key, str):
            msg = "API key is required and must be a non-empty string"
            raise ConfigurationError(
                msg,
                context={"parameter": "api_key", "type": type(api_key).__name__},
            )
        if len(api_key.strip()) < 10:  # Basic sanity check
            msg = "API key appears to be invalid (too short)"
            raise ConfigurationError(
                msg,
                context={"parameter": "api_key", "length": len(api_key.strip())},
            )

        # Security: Validate model
        if not model or not isinstance(model, str):
            msg = "Model is required and must be a non-empty string"
            raise ConfigurationError(
                msg,
                context={"parameter": "model", "type": type(model).__name__},
            )
        if len(model) > 100:
            msg = f"Model name too long (max 100 characters, got {len(model)})"
            raise ConfigurationError(
                msg,
                context={"parameter": "model", "length": len(model)},
            )

        # Security: Validate headers
        if http_referer and (not isinstance(http_referer, str) or len(http_referer) > 500):
            msg = f"HTTP referer must be a string with max 500 characters (got {len(http_referer)})"
            raise ConfigurationError(
                msg,
                context={
                    "parameter": "http_referer",
                    "length": len(http_referer) if http_referer else 0,
                },
            )
        if x_title and (not isinstance(x_title, str) or len(x_title) > 200):
            msg = f"X-Title must be a string with max 200 characters (got {len(x_title)})"
            raise ConfigurationError(
                msg,
                context={"parameter": "x_title", "length": len(x_title) if x_title else 0},
            )

        # Security: Validate timeout
        if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
            msg = f"Timeout must be a positive number (got {timeout_sec})"
            raise ConfigurationError(
                msg,
                context={
                    "parameter": "timeout_sec",
                    "value": timeout_sec,
                    "type": type(timeout_sec).__name__,
                },
            )
        if timeout_sec > 300:  # 5 minutes max
            msg = f"Timeout too large (max 300 seconds, got {timeout_sec})"
            raise ConfigurationError(
                msg,
                context={"parameter": "timeout_sec", "value": timeout_sec},
            )

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            msg = f"Max retries must be an integer between 0 and 10 (got {max_retries})"
            raise ConfigurationError(
                msg,
                context={
                    "parameter": "max_retries",
                    "value": max_retries,
                    "type": type(max_retries).__name__,
                },
            )
        if not isinstance(backoff_base, int | float) or backoff_base < 0:
            msg = f"Backoff base must be a non-negative number (got {backoff_base})"
            raise ConfigurationError(
                msg,
                context={
                    "parameter": "backoff_base",
                    "value": backoff_base,
                    "type": type(backoff_base).__name__,
                },
            )

        # Validate structured output settings
        if structured_output_mode not in {"json_schema", "json_object"}:
            msg = f"Structured output mode must be 'json_schema' or 'json_object' (got '{structured_output_mode}')"
            raise ConfigurationError(
                msg,
                context={"parameter": "structured_output_mode", "value": structured_output_mode},
            )

        # Validate max_response_size_mb
        if (
            not isinstance(max_response_size_mb, int)
            or max_response_size_mb < 1
            or max_response_size_mb > 100
        ):
            msg = f"Max response size must be between 1 and 100 MB (got {max_response_size_mb})"
            raise ConfigurationError(
                msg,
                context={"parameter": "max_response_size_mb", "value": max_response_size_mb},
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
            msg = "Client has been closed"
            raise RuntimeError(msg)

        # Check circuit breaker before proceeding
        if self._circuit_breaker and not self._circuit_breaker.can_proceed():
            logger.warning(
                "openrouter_circuit_breaker_open",
                extra={
                    "request_id": request_id,
                    "circuit_state": self._circuit_breaker.state.value,
                    "failure_count": self._circuit_breaker.failure_count,
                },
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

        # Early validation to fail fast
        if not messages:
            msg = "Messages cannot be empty"
            raise ValidationError(msg, context={"messages_count": 0})

        if not isinstance(messages, list):
            msg = f"Messages must be a list, got {type(messages).__name__}"
            raise ValidationError(
                msg,
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
            raise_if_cancelled(e)
            msg = f"Invalid chat request parameters: {e}"
            raise ValidationError(
                msg,
                context={"original_error": str(e), "messages_count": len(messages)},
            ) from e

        # Pre-process and validate with specific error handling
        try:
            self.request_builder.validate_chat_request(request)
            sanitized_messages = self.request_builder.sanitize_messages(messages)
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Request validation failed: {e}"
            raise ValidationError(
                msg,
                context={"original_error": str(e), "messages_count": len(messages)},
            ) from e

        # Determine models to try
        primary_model = model_override if model_override else self._model
        models_to_try = self.model_capabilities.build_model_fallback_list(
            primary_model, self._fallback_models, response_format, self._enable_structured_outputs
        )

        if not models_to_try:
            msg = "No models available to try"
            raise ValueError(msg)

        # Build chat state
        state = ChatState(
            builder_rf_mode_original=self.request_builder._structured_output_mode,
            response_format_initial=response_format if isinstance(response_format, dict) else None,
            message_lengths=[len(str(msg.get("content", ""))) for msg in sanitized_messages],
            message_roles=[msg.get("role", "?") for msg in sanitized_messages],
            total_chars=sum(len(str(msg.get("content", ""))) for msg in sanitized_messages),
        )

        # Delegate to orchestrator
        try:
            async with self._request_context() as client:
                return await self._chat_orchestrator.execute(
                    client=client,
                    request=request,
                    sanitized_messages=sanitized_messages,
                    models_to_try=models_to_try,
                    state=state,
                    primary_model=primary_model,
                    enable_structured_outputs=self._enable_structured_outputs,
                )
        except Exception as e:
            raise_if_cancelled(e)
            state.last_error_text = f"Critical error: {e!s}"
            state.last_error_context = {
                "status_code": None,
                "message": "Critical client error",
                "api_error": str(e),
                "error_type": "critical",
            }
            self.request_builder._structured_output_mode = state.builder_rf_mode_original
            return self._chat_orchestrator._build_exhausted_result(
                models_to_try, sanitized_messages, state
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
