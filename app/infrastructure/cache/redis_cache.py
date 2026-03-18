from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.infrastructure.redis import get_redis, redis_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.config import AppConfig

logger = get_logger(__name__)


class RedisCache:
    """Small helper for JSON-based Redis caching with fail-open behavior."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._client = None
        self._lock = asyncio.Lock()
        timeout = cfg.redis.cache_timeout_sec or 0.3
        self._timeout = max(0.05, float(timeout))

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.redis.enabled and self.cfg.redis.cache_enabled)

    async def _get_client(self):
        if not self.enabled:
            return None

        if self._client:
            return self._client

        async with self._lock:
            if self._client:
                return self._client
            try:
                self._client = await get_redis(self.cfg)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "redis_cache_connect_failed",
                    exc_info=True,
                    extra={"error": str(exc), "required": self.cfg.redis.required},
                )
                self._client = None
                return None
            return self._client

    async def get_json(self, *parts: str) -> Any | None:
        """Fetch a JSON value; returns None on miss or any error."""
        client = await self._get_client()
        if not client:
            return None

        key = redis_key(self.cfg.redis.prefix, *[p for p in parts if p])
        try:
            async with asyncio.timeout(self._timeout):
                raw = await client.get(key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "redis_cache_get_failed",
                exc_info=True,
                extra={"key": key, "error": str(exc)},
            )
            return None

        if raw is None:
            return None

        try:
            return json.loads(raw)
        except Exception:
            logger.warning("redis_cache_decode_failed", extra={"key": key})
            return None

    async def set_json(self, *, value: Any, ttl_seconds: int, parts: Iterable[str]) -> bool:
        """Store a JSON value with TTL; returns False on failure."""
        if ttl_seconds <= 0:
            return False

        client = await self._get_client()
        if not client:
            return False

        key = redis_key(self.cfg.redis.prefix, *[p for p in parts if p])
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except Exception:
            logger.warning("redis_cache_encode_failed", extra={"key": key})
            return False

        try:
            async with asyncio.timeout(self._timeout):
                await client.set(key, payload, ex=ttl_seconds)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "redis_cache_set_failed",
                exc_info=True,
                extra={"key": key, "error": str(exc)},
            )
            return False

    async def clear(self) -> int:
        """Clear all cached keys matching the prefix.

        Uses SCAN instead of KEYS to avoid blocking Redis on large datasets.
        """
        return await self._clear_pattern(f"{self.cfg.redis.prefix}:*")

    async def clear_prefix(self, *parts: str) -> int:
        """Clear cache keys under a specific sub-prefix."""
        key_prefix = redis_key(self.cfg.redis.prefix, *[p for p in parts if p])
        return await self._clear_pattern(f"{key_prefix}:*")

    async def _clear_pattern(self, pattern: str) -> int:
        client = await self._get_client()
        if not client:
            return 0

        deleted_count = 0
        try:
            # Use SCAN to iterate without blocking Redis
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break
            return deleted_count
        except Exception as exc:
            logger.warning(
                "redis_cache_clear_failed",
                exc_info=True,
                extra={"pattern": pattern, "error": str(exc), "deleted": deleted_count},
            )
            return deleted_count
