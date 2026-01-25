"""Base LLM client with shared functionality for all providers.

This module contains common HTTP client pooling, retry logic, and error handling
that is shared across all LLM provider implementations.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from contextlib import asynccontextmanager
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

import httpx

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from app.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Check for HTTP/2 support
HTTP2_AVAILABLE = find_spec("h2") is not None

if not HTTP2_AVAILABLE:
    logger.warning(
        "HTTP/2 support disabled because the 'h2' package is not installed; falling back to HTTP/1.1"
    )


class BaseLLMClient:
    """Base class for LLM clients with shared HTTP pooling and retry logic.

    This class provides:
    - Shared HTTP client pooling across instances for connection reuse
    - Exponential backoff retry logic
    - Circuit breaker integration
    - Response size validation
    - Proper async resource cleanup

    Subclasses should implement the provider-specific chat() method and
    use the shared _ensure_client() and _request_context() methods.
    """

    # Class-level client pool for connection reuse across all instances
    _client_pools: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[str, httpx.AsyncClient]
    ] = weakref.WeakKeyDictionary()
    _cleanup_registry: weakref.WeakSet[BaseLLMClient] = weakref.WeakSet()

    # Async lock for client pool access (created lazily per event loop)
    _client_pool_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
        weakref.WeakKeyDictionary()
    )
    # Thread lock to protect async lock initialization
    _lock_init_lock = threading.Lock()

    def __init__(
        self,
        *,
        base_url: str,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        keepalive_expiry: float = 30.0,
        max_response_size_mb: int = 10,
        circuit_breaker: CircuitBreaker | None = None,
        debug_payloads: bool = False,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the base LLM client.

        Args:
            base_url: Base URL for the API endpoint.
            timeout_sec: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            backoff_base: Base delay for exponential backoff.
            max_connections: Maximum concurrent connections.
            max_keepalive_connections: Maximum keepalive connections.
            keepalive_expiry: Keepalive connection expiry in seconds.
            max_response_size_mb: Maximum response size in MB.
            circuit_breaker: Optional circuit breaker instance.
            debug_payloads: Whether to log request/response payloads.
            audit: Optional audit callback function.
        """
        self._base_url = base_url
        self._timeout = httpx.Timeout(timeout_sec, connect=10.0, read=timeout_sec)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._max_response_size_bytes = int(max_response_size_mb) * 1024 * 1024
        self._circuit_breaker = circuit_breaker
        self._debug_payloads = debug_payloads
        self._audit = audit
        self._closed = False

        # Connection pool limits
        self._limits = httpx.Limits(
            max_keepalive_connections=max_keepalive_connections,
            max_connections=max_connections,
            keepalive_expiry=keepalive_expiry,
        )

        # Client management
        self._client_key = f"{self._base_url}:{hash((timeout_sec, max_connections))}"
        self._client: httpx.AsyncClient | None = None

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
        """
        loop = cls._get_event_loop()

        # Fast path: lock already exists
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

    @classmethod
    async def cleanup_all_clients(cls) -> None:
        """Clean up all shared HTTP clients across all instances."""
        with cls._lock_init_lock:
            pools = list(cls._client_pools.values())
            cls._client_pools = weakref.WeakKeyDictionary()
            cls._client_pool_locks = weakref.WeakKeyDictionary()

        clients = [client for pool in pools for client in pool.values()]

        if clients:
            await asyncio.gather(*[client.aclose() for client in clients], return_exceptions=True)

    async def __aenter__(self) -> BaseLLMClient:
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
                    http2=HTTP2_AVAILABLE,
                    follow_redirects=True,
                )
                pool[self._client_key] = client

            self._client = client
            return client

    @asynccontextmanager
    async def _request_context(self) -> AsyncGenerator[httpx.AsyncClient]:  # type: ignore[type-arg, unused-ignore]
        """Context manager for request handling with proper error handling."""
        if self._closed:
            msg = "Cannot use client after it has been closed"
            raise RuntimeError(msg)

        client = await self._ensure_client()

        try:
            yield client
        except httpx.TimeoutException as e:
            msg = f"Request timeout: {e}"
            raise TimeoutError(msg) from e
        except httpx.ConnectError as e:
            msg = f"Connection failed: {e}"
            raise ConnectionError(msg) from e
        except httpx.HTTPStatusError:
            # Let HTTP errors pass through for caller handling
            raise
        except Exception as e:
            raise_if_cancelled(e)
            msg = f"Unexpected client error: {e}"
            raise RuntimeError(msg) from e

    async def _sleep_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        import random

        base_delay = max(0.0, self._backoff_base * (2**attempt))
        jitter = 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(base_delay * jitter)

    def _check_circuit_breaker(self) -> bool:
        """Check if requests can proceed through the circuit breaker.

        Returns:
            True if requests can proceed, False if circuit is open.
        """
        if self._circuit_breaker and not self._circuit_breaker.can_proceed():
            logger.warning(
                "circuit_breaker_open",
                extra={
                    "provider": getattr(self, "provider_name", "unknown"),
                    "circuit_state": self._circuit_breaker.state.value,
                    "failure_count": self._circuit_breaker.failure_count,
                },
            )
            return False
        return True

    def _record_circuit_breaker_success(self) -> None:
        """Record a successful request with the circuit breaker."""
        if self._circuit_breaker:
            self._circuit_breaker.record_success()

    def _record_circuit_breaker_failure(self) -> None:
        """Record a failed request with the circuit breaker."""
        if self._circuit_breaker:
            self._circuit_breaker.record_failure()

    def _audit_event(self, level: str, event: str, details: dict[str, Any]) -> None:
        """Log an audit event if audit callback is configured."""
        if self._audit:
            self._audit(level, event, details)
        else:
            log_level = logging.INFO if level == "info" else logging.ERROR
            logger.log(log_level, event, extra=details)


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    """Exponential backoff with light jitter (utility function)."""
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
