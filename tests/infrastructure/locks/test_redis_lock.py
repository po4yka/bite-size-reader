"""Unit tests for RedisDistributedLock."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.locks.redis_lock import RedisDistributedLock

# ---------------------------------------------------------------------------
# Fake Redis helpers
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal in-process fake for redis.asyncio.Redis."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> str | None:
        if nx and key in self._store:
            return None  # key already exists — SET NX fails
        self._store[key] = value
        return "OK"

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def eval(self, script: str, numkeys: int, *args: str) -> int:
        """Simulate the Lua check-and-delete script."""
        key, token = args[0], args[1]
        if self._store.get(key) == token:
            del self._store[key]
            return 1
        return 0


# ---------------------------------------------------------------------------
# Acquire tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_succeeds_when_key_absent():
    redis = _FakeRedis()
    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)
    async with lock as acquired:
        assert acquired is True
        assert "task_lock:test" in redis._store


@pytest.mark.asyncio
async def test_acquire_fails_when_key_held_by_another_token():
    redis = _FakeRedis()
    # Pre-populate the key as if another worker holds the lock.
    redis._store["task_lock:test"] = "other-worker-token"

    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)
    async with lock as acquired:
        assert acquired is False
        # Our token must NOT have overwritten the existing holder.
        assert redis._store["task_lock:test"] == "other-worker-token"


# ---------------------------------------------------------------------------
# Release tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_deletes_our_token():
    redis = _FakeRedis()
    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)
    async with lock as acquired:
        assert acquired is True
        assert "task_lock:test" in redis._store

    # After __aexit__ the key must be gone.
    assert "task_lock:test" not in redis._store


@pytest.mark.asyncio
async def test_release_does_not_delete_different_token():
    redis = _FakeRedis()
    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)

    # Acquire the lock so __aenter__ records our token.
    async with lock as acquired:
        assert acquired is True
        # Simulate TTL expiry + a new holder acquiring the same key.
        redis._store["task_lock:test"] = "new-holder-token"

    # __aexit__ ran the Lua check — because the value no longer matches our
    # token it must NOT have deleted the new holder's entry.
    assert redis._store.get("task_lock:test") == "new-holder-token"


# ---------------------------------------------------------------------------
# Fail-open (Redis unavailable) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_succeeds_when_redis_client_is_none():
    """When Redis is disabled/unavailable (None client), the lock must grant access."""
    lock = RedisDistributedLock(None, "task_lock:test", ttl_seconds=60)
    async with lock as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_acquire_succeeds_on_redis_error():
    """A Redis communication error must not block the task (fail-open)."""
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))

    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)
    async with lock as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_release_survives_redis_error():
    """A Redis error during release must not propagate — TTL will clean up."""
    redis = _FakeRedis()
    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)

    async with lock:
        # Sabotage eval so the release call fails.
        redis.eval = AsyncMock(side_effect=ConnectionError("Redis down"))

    # The context manager must exit without raising.


# ---------------------------------------------------------------------------
# Log warning on contention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warning_logged_when_lock_held(caplog):
    import logging

    redis = _FakeRedis()
    redis._store["task_lock:test"] = "other-token"

    lock = RedisDistributedLock(redis, "task_lock:test", ttl_seconds=60)
    with caplog.at_level(logging.WARNING):
        async with lock as acquired:
            assert acquired is False

    assert any("lock_held_by_other_worker" in r.message for r in caplog.records)
