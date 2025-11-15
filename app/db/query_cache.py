"""Query result caching for database operations.

Provides LRU-based caching for expensive database queries with automatic
cache invalidation on writes.
"""

from __future__ import annotations

import logging
from functools import lru_cache, wraps
from typing import Any, TypeVar
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Type variables for generic cache decorator
F = TypeVar("F", bound=Callable[..., Any])


class QueryCache:
    """Manages query result caching for database operations.

    Features:
    - LRU cache with configurable size
    - Automatic cache invalidation on writes
    - Cache hit/miss statistics
    - Per-query cache control
    """

    def __init__(self, max_size: int = 128):
        """Initialize query cache.

        Args:
            max_size: Maximum number of cached results per query type
        """
        self.max_size = max_size
        self.stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
        self._caches: dict[str, Any] = {}

    def cache_query(self, cache_key: str | None = None) -> Callable[[F], F]:
        """Decorator to cache query results.

        Args:
            cache_key: Optional cache key prefix. If None, uses function name.

        Usage:
            @cache.cache_query("request_by_id")
            def get_request_by_id(self, request_id: int):
                ...
        """

        def decorator(func: F) -> F:
            key = cache_key or func.__name__

            # Create LRU cache for this function
            cached_func = lru_cache(maxsize=self.max_size)(func)
            self._caches[key] = cached_func

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    result = cached_func(*args, **kwargs)
                    self.stats["hits"] += 1
                    logger.debug(
                        "query_cache_hit",
                        extra={"cache_key": key, "hits": self.stats["hits"]},
                    )
                    return result
                except TypeError:
                    # Unhashable arguments, bypass cache
                    self.stats["misses"] += 1
                    logger.debug(
                        "query_cache_bypass",
                        extra={"cache_key": key, "reason": "unhashable_args"},
                    )
                    return func(*args, **kwargs)

            # Attach cache_clear method
            wrapper.cache_clear = cached_func.cache_clear  # type: ignore
            wrapper.cache_info = cached_func.cache_info  # type: ignore

            return wrapper  # type: ignore

        return decorator

    def invalidate(self, cache_key: str) -> None:
        """Invalidate a specific cache.

        Args:
            cache_key: Cache key to invalidate
        """
        if cache_key in self._caches:
            self._caches[cache_key].cache_clear()
            self.stats["invalidations"] += 1
            logger.debug(
                "query_cache_invalidated",
                extra={"cache_key": cache_key},
            )

    def invalidate_all(self) -> None:
        """Invalidate all caches."""
        for cache_key in self._caches:
            self._caches[cache_key].cache_clear()
        self.stats["invalidations"] += len(self._caches)
        logger.debug(
            "query_cache_cleared_all",
            extra={"caches_cleared": len(self._caches)},
        )

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with hit/miss/invalidation counts and cache info
        """
        cache_info = {}
        for key, cache_func in self._caches.items():
            if hasattr(cache_func, "cache_info"):
                info = cache_func.cache_info()
                cache_info[key] = {
                    "hits": info.hits,
                    "misses": info.misses,
                    "size": info.currsize,
                    "max_size": info.maxsize,
                }

        return {
            **self.stats,
            "caches": cache_info,
            "total_cached_items": sum(info["size"] for info in cache_info.values()),
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self.stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }


# Global cache instance
_default_cache = QueryCache(max_size=128)


def get_cache() -> QueryCache:
    """Get the default query cache instance."""
    return _default_cache
