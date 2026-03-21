"""In-memory rate limiter for automation rule execution."""

from __future__ import annotations

import time


class InMemoryRuleRateLimiter:
    """Track recent per-user rule executions in process memory."""

    def __init__(self) -> None:
        self._timestamps: dict[int, list[float]] = {}

    async def async_allow_execution(
        self,
        user_id: int,
        *,
        limit: int,
        window_seconds: float,
    ) -> bool:
        now = time.time()
        window_start = now - window_seconds
        timestamps = [ts for ts in self._timestamps.get(user_id, []) if ts > window_start]
        if len(timestamps) >= limit:
            self._timestamps[user_id] = timestamps
            return False

        timestamps.append(now)
        self._timestamps[user_id] = timestamps
        return True
