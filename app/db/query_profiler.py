"""Database query profiler for slow query detection.

Provides a decorator `@profile_query` to measure and log queries that exceed
a configurable threshold (default 100ms).

Usage:
    from app.db.query_profiler import profile_query

    @profile_query(threshold_ms=100)
    async def my_slow_query():
        return await db.execute("SELECT * FROM large_table")

Integrates with Prometheus metrics if available.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def profile_query(
    threshold_ms: float = 100.0,
    operation: str | None = None,
) -> Callable[[F], F]:
    """Decorator to profile database query execution time.

    Logs queries that exceed the threshold and updates Prometheus metrics.

    Args:
        threshold_ms: Log queries taking longer than this (default 100ms).
        operation: Operation name for metrics (e.g., "select", "insert").
                  Auto-detected from function name if not provided.

    Returns:
        Decorated function with profiling.

    Example:
        @profile_query(threshold_ms=50.0, operation="select")
        async def get_user(user_id: int):
            return await db.get_user_by_id(user_id)
    """

    def decorator(func: F) -> F:
        op_name = operation or _extract_operation_name(func.__name__)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                _record_query(op_name, elapsed_ms, threshold_ms, func.__name__)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                _record_query(op_name, elapsed_ms, threshold_ms, func.__name__)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def _extract_operation_name(func_name: str) -> str:
    """Extract operation type from function name.

    Maps common function name patterns to operation types:
    - get_*, fetch_*, find_* -> select
    - insert_*, create_*, add_* -> insert
    - update_*, modify_*, set_* -> update
    - delete_*, remove_* -> delete
    """
    func_lower = func_name.lower()

    if any(func_lower.startswith(p) for p in ("get_", "fetch_", "find_", "list_", "search_")):
        return "select"
    if any(func_lower.startswith(p) for p in ("insert_", "create_", "add_")):
        return "insert"
    if any(func_lower.startswith(p) for p in ("update_", "modify_", "set_")):
        return "update"
    if any(func_lower.startswith(p) for p in ("delete_", "remove_")):
        return "delete"

    return "query"


def _record_query(
    operation: str,
    elapsed_ms: float,
    threshold_ms: float,
    func_name: str,
) -> None:
    """Record query execution and log if slow."""
    # Record metrics if prometheus is available
    try:
        from app.observability.metrics import record_db_query

        record_db_query(operation, elapsed_ms / 1000)
    except ImportError:
        pass

    # Log slow queries
    if elapsed_ms >= threshold_ms:
        logger.warning(
            "slow_query_detected",
            extra={
                "operation": operation,
                "function": func_name,
                "elapsed_ms": round(elapsed_ms, 2),
                "threshold_ms": threshold_ms,
            },
        )


class QueryProfiler:
    """Context manager for profiling database queries.

    Usage:
        with QueryProfiler("select_users") as profiler:
            result = db.execute("SELECT * FROM users")

        print(f"Query took {profiler.elapsed_ms}ms")
    """

    def __init__(
        self,
        operation: str = "query",
        threshold_ms: float = 100.0,
        auto_log: bool = True,
    ):
        """Initialize query profiler.

        Args:
            operation: Operation name for logging/metrics.
            threshold_ms: Log warning if query exceeds this.
            auto_log: If True, automatically log slow queries.
        """
        self.operation = operation
        self.threshold_ms = threshold_ms
        self.auto_log = auto_log
        self.elapsed_ms: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> QueryProfiler:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000

        if self.auto_log:
            _record_query(
                self.operation,
                self.elapsed_ms,
                self.threshold_ms,
                f"QueryProfiler:{self.operation}",
            )


class AsyncQueryProfiler:
    """Async context manager for profiling database queries.

    Usage:
        async with AsyncQueryProfiler("select_users") as profiler:
            result = await db.execute("SELECT * FROM users")

        print(f"Query took {profiler.elapsed_ms}ms")
    """

    def __init__(
        self,
        operation: str = "query",
        threshold_ms: float = 100.0,
        auto_log: bool = True,
    ):
        """Initialize async query profiler.

        Args:
            operation: Operation name for logging/metrics.
            threshold_ms: Log warning if query exceeds this.
            auto_log: If True, automatically log slow queries.
        """
        self.operation = operation
        self.threshold_ms = threshold_ms
        self.auto_log = auto_log
        self.elapsed_ms: float = 0.0
        self._start: float = 0.0

    async def __aenter__(self) -> AsyncQueryProfiler:
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000

        if self.auto_log:
            _record_query(
                self.operation,
                self.elapsed_ms,
                self.threshold_ms,
                f"AsyncQueryProfiler:{self.operation}",
            )
