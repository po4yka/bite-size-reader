"""Redis cache and distributed locking for Karakeep sync.

Provides shared bookmark index cache and prevents concurrent sync operations.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.infrastructure.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class KarakeepSyncCache:
    """Distributed cache and locking for Karakeep sync operations.

    Key patterns:
    - Bookmark index: bsr:karakeep:index:{user_id}
      Value: {"url_hash": "bookmark_id", ...}
      TTL: 1 hour (configurable via REDIS_KARAKEEP_CACHE_TTL_SECONDS)

    - Sync lock: bsr:karakeep:lock:{user_id}
      Value: {"owner": str, "acquired_at": timestamp}
      TTL: 10 minutes (configurable via REDIS_KARAKEEP_LOCK_TTL_SECONDS)

    The lock prevents multiple workers from running sync for the same user
    simultaneously, which would cause duplicate bookmarks or race conditions.

    Fallback: On Redis unavailable, returns None for cache (in-memory used),
    and lock acquisition always succeeds (single-instance mode).
    """

    def __init__(self, cache: RedisCache, cfg: AppConfig, owner_id: str | None = None) -> None:
        self._cache = cache
        self._cfg = cfg
        self._owner_id = owner_id or f"worker-{id(self)}"

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    def _index_key(self, user_id: int) -> str:
        """Build the bookmark index cache key."""
        from app.infrastructure.redis import redis_key

        return redis_key(self._cfg.redis.prefix, "karakeep", "index", str(user_id))

    def _lock_key(self, user_id: int) -> str:
        """Build the sync lock key."""
        from app.infrastructure.redis import redis_key

        return redis_key(self._cfg.redis.prefix, "karakeep", "lock", str(user_id))

    # -------------------------------------------------------------------------
    # Bookmark Index Cache
    # -------------------------------------------------------------------------

    async def get_bookmark_index(self, user_id: int) -> dict[str, str] | None:
        """Get cached URL-to-bookmark-ID mapping.

        Args:
            user_id: User ID for the bookmark index.

        Returns:
            Dict mapping normalized URL hashes to bookmark IDs, or None if not cached.
        """
        if not self._cache.enabled:
            return None

        cached = await self._cache.get_json("karakeep", "index", str(user_id))
        if isinstance(cached, dict):
            logger.debug(
                "karakeep_index_cache_hit",
                extra={"user_id": user_id, "count": len(cached)},
            )
            return cached
        return None

    async def set_bookmark_index(
        self,
        user_id: int,
        index: dict[str, str],
    ) -> bool:
        """Cache URL-to-bookmark-ID mapping.

        Args:
            user_id: User ID for the bookmark index.
            index: Dict mapping normalized URL hashes to bookmark IDs.

        Returns:
            True if cached successfully, False otherwise.
        """
        if not self._cache.enabled:
            return False

        ttl = self._cfg.redis.karakeep_cache_ttl_seconds
        success = await self._cache.set_json(
            value=index,
            ttl_seconds=ttl,
            parts=("karakeep", "index", str(user_id)),
        )

        if success:
            logger.debug(
                "karakeep_index_cached",
                extra={"user_id": user_id, "count": len(index), "ttl": ttl},
            )
        return success

    async def invalidate_bookmark_index(self, user_id: int) -> bool:
        """Invalidate the cached bookmark index.

        Called after sync completes to ensure fresh data on next access.

        Returns:
            True if invalidated, False otherwise.
        """
        if not self._cache.enabled:
            return False

        client = await self._cache._get_client()
        if not client:
            return False

        key = self._index_key(user_id)
        try:
            await client.delete(key)
            logger.debug(
                "karakeep_index_invalidated",
                extra={"user_id": user_id},
            )
            return True
        except Exception as exc:
            logger.warning(
                "karakeep_index_invalidate_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return False

    # -------------------------------------------------------------------------
    # Distributed Sync Lock
    # -------------------------------------------------------------------------

    async def acquire_sync_lock(self, user_id: int, wait: bool = False) -> bool:
        """Acquire the sync lock for a user.

        Uses Redis SET NX (set if not exists) for atomic lock acquisition.

        Args:
            user_id: User ID to lock sync for.
            wait: If True, wait for lock to become available (up to TTL).

        Returns:
            True if lock acquired, False if already held by another worker.
        """
        if not self._cache.enabled:
            # No Redis = single instance, always succeed
            return True

        client = await self._cache._get_client()
        if not client:
            return True  # Fallback: no locking

        key = self._lock_key(user_id)
        ttl = self._cfg.redis.karakeep_lock_ttl_seconds

        lock_value = {
            "owner": self._owner_id,
            "acquired_at": time.time(),
        }

        import json

        try:
            # Try to acquire with SET NX EX
            acquired = await client.set(
                key,
                json.dumps(lock_value),
                nx=True,  # Only set if not exists
                ex=ttl,  # Expire after TTL
            )

            if acquired:
                logger.info(
                    "karakeep_sync_lock_acquired",
                    extra={"user_id": user_id, "owner": self._owner_id, "ttl": ttl},
                )
                return True

            if not wait:
                logger.debug(
                    "karakeep_sync_lock_busy",
                    extra={"user_id": user_id},
                )
                return False

            # Wait mode: poll until lock available or timeout
            wait_start = time.time()
            while time.time() - wait_start < ttl:
                await client.aclose()  # Not needed, just sleep
                import asyncio

                await asyncio.sleep(1.0)

                acquired = await client.set(
                    key,
                    json.dumps(lock_value),
                    nx=True,
                    ex=ttl,
                )
                if acquired:
                    logger.info(
                        "karakeep_sync_lock_acquired_after_wait",
                        extra={
                            "user_id": user_id,
                            "owner": self._owner_id,
                            "waited_seconds": time.time() - wait_start,
                        },
                    )
                    return True

            logger.warning(
                "karakeep_sync_lock_timeout",
                extra={"user_id": user_id, "waited_seconds": ttl},
            )
            return False

        except Exception as exc:
            logger.warning(
                "karakeep_sync_lock_error",
                exc_info=True,
                extra={"user_id": user_id, "error": str(exc)},
            )
            # On error, allow sync to proceed (single-instance fallback)
            return True

    async def release_sync_lock(self, user_id: int) -> bool:
        """Release the sync lock for a user.

        Only releases if we own the lock (prevents releasing another worker's lock).

        Returns:
            True if released, False if not owned or error.
        """
        if not self._cache.enabled:
            return True

        client = await self._cache._get_client()
        if not client:
            return True

        key = self._lock_key(user_id)

        try:
            import json

            # Check if we own the lock
            raw = await client.get(key)
            if not raw:
                return True  # Lock already released

            lock_data = json.loads(raw)
            if lock_data.get("owner") != self._owner_id:
                logger.warning(
                    "karakeep_sync_lock_not_owned",
                    extra={
                        "user_id": user_id,
                        "expected_owner": self._owner_id,
                        "actual_owner": lock_data.get("owner"),
                    },
                )
                return False

            # Delete the lock
            await client.delete(key)
            logger.info(
                "karakeep_sync_lock_released",
                extra={"user_id": user_id, "owner": self._owner_id},
            )
            return True

        except Exception as exc:
            logger.warning(
                "karakeep_sync_lock_release_error",
                exc_info=True,
                extra={"user_id": user_id, "error": str(exc)},
            )
            return False

    async def is_sync_locked(self, user_id: int) -> bool:
        """Check if sync is currently locked for a user.

        Returns:
            True if locked, False otherwise.
        """
        if not self._cache.enabled:
            return False

        client = await self._cache._get_client()
        if not client:
            return False

        key = self._lock_key(user_id)
        try:
            exists = await client.exists(key)
            return bool(exists)
        except Exception:
            return False

    async def get_lock_info(self, user_id: int) -> dict[str, Any] | None:
        """Get information about the current lock holder.

        Returns:
            Lock info dict or None if not locked.
        """
        if not self._cache.enabled:
            return None

        client = await self._cache._get_client()
        if not client:
            return None

        key = self._lock_key(user_id)
        try:
            import json

            raw = await client.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            return None
