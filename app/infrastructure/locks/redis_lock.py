"""Redis-backed distributed lock using SET NX EX + Lua atomic release."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = get_logger(__name__)

# Lua script: delete the key only when its value matches our token.
# Returns 1 if deleted, 0 if the key was gone or held by a different token.
_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class RedisDistributedLock:
    """Async context manager that acquires a Redis-backed distributed lock.

    Usage::

        async with RedisDistributedLock(redis_client, "task_lock:my_task", ttl_seconds=1800) as acquired:
            if not acquired:
                return  # another worker holds the lock
            # ... do work ...

    The lock is acquired via ``SET key token NX EX ttl_seconds``.  Release
    uses an atomic Lua script (check-and-delete) so a slow task that outlives
    its TTL cannot accidentally evict a newer holder's lock.

    If *redis_client* is ``None`` (Redis disabled), acquisition always
    succeeds so callers behave correctly in single-worker environments.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None,
        key: str,
        ttl_seconds: int,
    ) -> None:
        self._client = redis_client
        self._key = key
        self._ttl = ttl_seconds
        self._token: str | None = None

    async def __aenter__(self) -> bool:
        if self._client is None:
            # Redis unavailable — act as an uncontested lock so the task runs.
            self._token = str(uuid4())
            return True

        self._token = str(uuid4())
        try:
            result = await self._client.set(
                self._key,
                self._token,
                nx=True,
                ex=self._ttl,
            )
        except Exception as exc:
            # Fail-open: if Redis is unreachable, let the task proceed rather
            # than silently dropping it.
            logger.warning(
                "redis_lock_acquire_error",
                extra={"key": self._key, "error": str(exc)},
            )
            return True

        acquired = result is not None  # SET NX returns None when key exists
        if not acquired:
            logger.warning(
                "lock_held_by_other_worker",
                extra={"key": self._key, "ttl": self._ttl},
            )
            self._token = None
        return acquired

    async def __aexit__(self, *args: object) -> None:
        if self._client is None or self._token is None:
            return

        try:
            result = self._client.eval(_RELEASE_SCRIPT, 1, self._key, self._token)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            # Non-fatal: TTL will expire the key automatically.
            logger.warning(
                "redis_lock_release_error",
                extra={"key": self._key, "error": str(exc)},
            )
        finally:
            self._token = None
