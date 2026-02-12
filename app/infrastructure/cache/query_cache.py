"""Redis-backed query result cache for async database operations.

Provides shared caching across multiple workers/processes, unlike the
in-memory LRU cache in app/db/query_cache.py which is per-process.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.infrastructure.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class RedisQueryCache:
    """Shared query result cache using Redis.

    Key pattern: bsr:query:{query_hash}
    Value: JSON-serialized query result
    TTL: Configurable via REDIS_QUERY_CACHE_TTL_SECONDS (default: 5 minutes)

    Unlike the in-memory LRU QueryCache, this:
    - Shares cached results across processes/workers
    - Survives process restarts
    - Has configurable TTL-based expiration

    Fallback: On Redis unavailable, returns None (cache miss).
    """

    def __init__(self, cache: RedisCache, cfg: AppConfig) -> None:
        self._cache = cache
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    @staticmethod
    def _make_hash(query_name: str, *args: Any, **kwargs: Any) -> str:
        """Create a deterministic hash for a query and its arguments.

        Args:
            query_name: Name of the query/function.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            SHA256 hash (first 32 chars) of the query fingerprint.
        """
        # Serialize arguments to create a unique fingerprint
        fingerprint_parts = [query_name]

        # Add positional args
        for arg in args:
            try:
                fingerprint_parts.append(json.dumps(arg, sort_keys=True, default=str))
            except (TypeError, ValueError):
                fingerprint_parts.append(str(arg))

        # Add sorted kwargs
        for key in sorted(kwargs.keys()):
            try:
                fingerprint_parts.append(
                    f"{key}={json.dumps(kwargs[key], sort_keys=True, default=str)}"
                )
            except (TypeError, ValueError):
                fingerprint_parts.append(f"{key}={kwargs[key]}")

        fingerprint = "|".join(fingerprint_parts)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]

    async def get(
        self,
        query_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any | None:
        """Get cached query result.

        Args:
            query_name: Name of the query/function.
            *args: Positional arguments that were passed to the query.
            **kwargs: Keyword arguments that were passed to the query.

        Returns:
            Cached result or None if not found.
        """
        if not self._cache.enabled:
            return None

        query_hash = self._make_hash(query_name, *args, **kwargs)
        cached = await self._cache.get_json("query", query_hash)

        if cached is not None:
            logger.debug(
                "redis_query_cache_hit",
                extra={"query_name": query_name, "hash": query_hash[:8]},
            )
        return cached

    async def set(
        self,
        result: Any,
        query_name: str,
        *args: Any,
        ttl_seconds: int | None = None,
        **kwargs: Any,
    ) -> bool:
        """Cache a query result.

        Args:
            result: The query result to cache.
            query_name: Name of the query/function.
            *args: Positional arguments that were passed to the query.
            ttl_seconds: Optional custom TTL. Uses config default if not specified.
            **kwargs: Keyword arguments that were passed to the query.

        Returns:
            True if cached successfully, False otherwise.
        """
        if not self._cache.enabled:
            return False

        query_hash = self._make_hash(query_name, *args, **kwargs)
        ttl = ttl_seconds or self._cfg.redis.query_cache_ttl_seconds

        success = await self._cache.set_json(
            value=result,
            ttl_seconds=ttl,
            parts=("query", query_hash),
        )

        if success:
            logger.debug(
                "redis_query_cached",
                extra={"query_name": query_name, "hash": query_hash[:8], "ttl": ttl},
            )
        return success

    async def invalidate(self, query_name: str, *args: Any, **kwargs: Any) -> bool:
        """Invalidate a specific cached query result.

        Args:
            query_name: Name of the query/function.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            True if invalidated, False otherwise.
        """
        if not self._cache.enabled:
            return False

        client = await self._cache._get_client()
        if not client:
            return False

        from app.infrastructure.redis import redis_key

        query_hash = self._make_hash(query_name, *args, **kwargs)
        key = redis_key(self._cfg.redis.prefix, "query", query_hash)

        try:
            await client.delete(key)
            logger.debug(
                "redis_query_cache_invalidated",
                extra={"query_name": query_name, "hash": query_hash[:8]},
            )
            return True
        except Exception as exc:
            logger.warning(
                "redis_query_cache_invalidate_failed",
                exc_info=True,
                extra={"query_name": query_name, "error": str(exc)},
            )
            return False

    async def invalidate_pattern(self, pattern: str = "*") -> int:
        """Invalidate all query cache entries matching a pattern.

        Args:
            pattern: Pattern to match (uses Redis SCAN). Default "*" clears all.

        Returns:
            Number of entries invalidated.
        """
        if not self._cache.enabled:
            return 0

        client = await self._cache._get_client()
        if not client:
            return 0

        full_pattern = f"{self._cfg.redis.prefix}:query:{pattern}"
        deleted_count = 0

        try:
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=full_pattern, count=100)
                if keys:
                    await client.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break

            logger.debug(
                "redis_query_cache_pattern_invalidated",
                extra={"pattern": pattern, "deleted": deleted_count},
            )
            return deleted_count
        except Exception as exc:
            logger.warning(
                "redis_query_cache_pattern_invalidate_failed",
                exc_info=True,
                extra={"pattern": pattern, "error": str(exc), "deleted": deleted_count},
            )
            return deleted_count
