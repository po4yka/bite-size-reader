"""In-memory rate-limit fallback for the API layer.

Used when Redis is unavailable. Replaces three module-level globals
(`_local_rate_limits`, `_local_rate_lock`, `_local_cleanup_last`) plus
the `global _local_cleanup_last` declaration in
`app/api/middleware._check_local_rate_limit` with a single class
instance so the `global` keyword can be removed from the middleware
module per [[eliminate-module-globals]].

Thread-safe. Performs periodic cleanup of stale buckets to keep
memory bounded.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class LocalRateLimiter:
    """Bucketed per-user in-memory rate limiter.

    The implementation is process-local: each process has its own
    buckets. Used as a fallback when the Redis-backed limiter is
    unavailable; not a substitute for distributed rate limiting.
    """

    _CLEANUP_INTERVAL_SEC = 60.0

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._cleanup_last = 0.0

    def check(self, user_id: str, *, limit: int, window: int) -> tuple[bool, int]:
        """Return ``(allowed, remaining)`` for the request.

        Args:
            user_id: caller identity used to key the bucket.
            limit: maximum requests permitted per window.
            window: window length in seconds.
        """
        now = time.time()
        window_start = int(now // window) * window
        key = f"{user_id}:{window_start}"

        with self._lock:
            if now - self._cleanup_last > self._CLEANUP_INTERVAL_SEC:
                stale_keys = [
                    k
                    for k in self._buckets
                    if int(k.split(":")[-1]) < window_start - window
                ]
                for k in stale_keys:
                    del self._buckets[k]
                self._cleanup_last = now

            requests = self._buckets[key]
            # Drop entries outside the current window.
            requests[:] = [ts for ts in requests if ts >= window_start]

            if len(requests) >= limit:
                return False, 0

            requests.append(now)
            return True, limit - len(requests)

    def reset(self) -> None:
        """Drop all buckets — used by tests between cases."""
        with self._lock:
            self._buckets.clear()
            self._cleanup_last = 0.0


__all__ = ["LocalRateLimiter"]
