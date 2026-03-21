from __future__ import annotations

import asyncio
import time
from typing import Any

from app.infrastructure.redis import redis_key

from .models import LockHandle, StageError


class BackgroundLockManager:
    def __init__(
        self,
        *,
        cfg: Any,
        redis: Any | None,
        logger: Any,
    ) -> None:
        self._cfg = cfg
        self._redis = redis
        self._logger = logger
        self._local_locks: dict[int, asyncio.Lock] = {}
        self._lock_enabled = cfg.background.redis_lock_enabled
        self._lock_required = cfg.background.redis_lock_required
        self._lock_ttl_ms = cfg.background.lock_ttl_ms
        self._lock_skip_on_held = cfg.background.lock_skip_on_held

    async def acquire(self, request_id: int, correlation_id: str | None) -> LockHandle | None:
        if self._lock_enabled and self._redis:
            key = redis_key(self._cfg.redis.prefix, "bg", "req", str(request_id))
            token = f"worker-{time.time_ns()}"
            try:
                acquired = await self._redis.set(key, token, nx=True, px=self._lock_ttl_ms)
            except Exception as exc:
                self._logger.warning(
                    "bg_lock_redis_error",
                    exc_info=True,
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "error": str(exc),
                    },
                )
                if self._lock_required:
                    raise StageError("lock", exc) from exc
                acquired = False

            if acquired:
                self._logger.info(
                    "bg_lock_acquired",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                        "ttl_ms": self._lock_ttl_ms,
                    },
                )
                return LockHandle("redis", key, token, None)

            if self._lock_skip_on_held:
                self._logger.info(
                    "bg_lock_held_skip",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                    },
                )
                return None

        lock = self._local_locks.setdefault(request_id, asyncio.Lock())
        if lock.locked() and self._lock_skip_on_held:
            self._logger.info(
                "bg_lock_held_skip",
                extra={
                    "correlation_id": correlation_id,
                    "request_id": request_id,
                    "source": "local",
                },
            )
            return None

        await lock.acquire()
        self._logger.info(
            "bg_lock_acquired",
            extra={
                "correlation_id": correlation_id,
                "request_id": request_id,
                "source": "local",
                "ttl_ms": self._lock_ttl_ms,
            },
        )
        return LockHandle("local", str(request_id), None, lock)

    async def release(self, handle: LockHandle | None) -> None:
        if handle is None:
            return

        if handle.source == "redis" and self._redis:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            try:
                await self._redis.eval(script, 1, handle.key, handle.token)
            except Exception:
                self._logger.warning(
                    "bg_lock_release_failed",
                    exc_info=True,
                    extra={"key": handle.key, "source": "redis"},
                )
        elif handle.source == "local" and handle.local_lock and handle.local_lock.locked():
            handle.local_lock.release()

        if handle.source == "local":
            request_id = int(handle.key)
            lock_obj = self._local_locks.get(request_id)
            if lock_obj is not None and not lock_obj.locked():
                self._local_locks.pop(request_id, None)
