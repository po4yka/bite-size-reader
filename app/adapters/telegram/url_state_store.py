"""State storage for users awaiting URL input in Telegram flows."""

from __future__ import annotations

import asyncio
import time


class URLAwaitingStateStore:
    """Tracks short-lived user state for awaited URL prompts."""

    def __init__(self, *, ttl_sec: int = 120) -> None:
        self._state_lock = asyncio.Lock()
        self._ttl_sec = max(1, int(ttl_sec))
        self._awaiting_url_users: dict[int, float] = {}

    @property
    def raw_state(self) -> dict[int, float]:
        """Expose state for compatibility with legacy tests/introspection."""
        return self._awaiting_url_users

    async def add(self, uid: int) -> None:
        async with self._state_lock:
            self._awaiting_url_users[uid] = time.time()

    async def remove(self, uid: int) -> bool:
        async with self._state_lock:
            existed = uid in self._awaiting_url_users
            if existed:
                self._awaiting_url_users.pop(uid, None)
            return existed

    async def consume(self, uid: int) -> None:
        async with self._state_lock:
            self._awaiting_url_users.pop(uid, None)

    async def contains(self, uid: int) -> bool:
        async with self._state_lock:
            ts = self._awaiting_url_users.get(uid)
            if ts is None:
                return False
            if time.time() - ts > self._ttl_sec:
                self._awaiting_url_users.pop(uid, None)
                return False
            return True

    async def cleanup_expired(self) -> int:
        async with self._state_lock:
            now = time.time()
            expired_uids = [
                uid for uid, ts in self._awaiting_url_users.items() if now - ts > self._ttl_sec
            ]
            for uid in expired_uids:
                self._awaiting_url_users.pop(uid, None)
            return len(expired_uids)
