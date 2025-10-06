"""Per-user rate limiting to prevent abuse and resource exhaustion."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    max_requests: int = 10  # Maximum requests per window
    window_seconds: int = 60  # Time window in seconds
    max_concurrent: int = 3  # Maximum concurrent operations per user
    cooldown_multiplier: float = 1.0  # Cooldown multiplier after limit exceeded


class UserRateLimiter:
    """Thread-safe per-user rate limiter with sliding window and concurrency control.

    Features:
    - Sliding window rate limiting
    - Concurrent operation tracking
    - Automatic cooldown periods
    - Cost-based limiting (optional)
    - Audit logging
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        """Initialize rate limiter with configuration.

        Args:
            config: Rate limit configuration. Uses defaults if None.
        """
        self._config = config or RateLimitConfig()
        self._user_requests: dict[int, deque[float]] = defaultdict(deque)
        self._user_concurrent: dict[int, int] = defaultdict(int)
        self._user_cooldowns: dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def check_and_record(
        self, user_id: int, *, cost: int = 1, operation: str = "request"
    ) -> tuple[bool, str | None]:
        """Check if user is within rate limits and record the request.

        Args:
            user_id: Telegram user ID
            cost: Cost weight for this operation (default: 1)
            operation: Description of operation for logging

        Returns:
            Tuple of (allowed, error_message). If allowed is False, error_message explains why.
        """
        async with self._lock:
            now = time.time()

            # Check if user is in cooldown period
            if user_id in self._user_cooldowns:
                cooldown_until = self._user_cooldowns[user_id]
                if now < cooldown_until:
                    remaining = int(cooldown_until - now)
                    logger.warning(
                        "rate_limit_cooldown",
                        extra={
                            "user_id": user_id,
                            "operation": operation,
                            "remaining_seconds": remaining,
                        },
                    )
                    return (
                        False,
                        f"⏳ Rate limit cooldown active. Try again in {remaining} seconds.",
                    )
                else:
                    # Cooldown expired, remove it
                    del self._user_cooldowns[user_id]

            # Get user's request queue
            user_queue = self._user_requests[user_id]

            # Remove old requests outside the window
            cutoff_time = now - self._config.window_seconds
            while user_queue and user_queue[0] < cutoff_time:
                user_queue.popleft()

            # Calculate current load (accounting for cost)
            current_load = len(user_queue) + cost

            # Check rate limit
            if current_load > self._config.max_requests:
                # Calculate when the oldest request will expire
                if user_queue:
                    oldest_request = user_queue[0]
                    retry_after = int(oldest_request + self._config.window_seconds - now + 1)
                else:
                    retry_after = self._config.window_seconds

                # Apply cooldown
                cooldown_duration = self._config.window_seconds * self._config.cooldown_multiplier
                self._user_cooldowns[user_id] = now + cooldown_duration

                logger.warning(
                    "rate_limit_exceeded",
                    extra={
                        "user_id": user_id,
                        "operation": operation,
                        "current_load": current_load,
                        "max_requests": self._config.max_requests,
                        "window_seconds": self._config.window_seconds,
                        "retry_after": retry_after,
                        "cooldown_seconds": int(cooldown_duration),
                    },
                )

                return (
                    False,
                    f"🚫 Rate limit exceeded. You can make {self._config.max_requests} requests "
                    f"per {self._config.window_seconds} seconds. "
                    f"Cooldown active for {int(cooldown_duration)} seconds.",
                )

            # Check concurrent operations limit
            concurrent_count = self._user_concurrent.get(user_id, 0)
            if concurrent_count >= self._config.max_concurrent:
                logger.warning(
                    "concurrent_limit_exceeded",
                    extra={
                        "user_id": user_id,
                        "operation": operation,
                        "concurrent_count": concurrent_count,
                        "max_concurrent": self._config.max_concurrent,
                    },
                )
                return (
                    False,
                    f"⏸️ Too many concurrent operations ({concurrent_count}). "
                    f"Maximum: {self._config.max_concurrent}. Please wait for previous requests to complete.",
                )

            # Record the request(s) based on cost
            for _ in range(cost):
                user_queue.append(now)

            logger.debug(
                "rate_limit_check_passed",
                extra={
                    "user_id": user_id,
                    "operation": operation,
                    "current_load": current_load,
                    "max_requests": self._config.max_requests,
                    "concurrent_count": concurrent_count,
                },
            )

            return True, None

    async def acquire_concurrent_slot(self, user_id: int) -> bool:
        """Acquire a concurrent operation slot for the user.

        Args:
            user_id: Telegram user ID

        Returns:
            True if slot acquired, False if limit exceeded
        """
        async with self._lock:
            concurrent_count = self._user_concurrent.get(user_id, 0)
            if concurrent_count >= self._config.max_concurrent:
                logger.warning(
                    "concurrent_slot_acquisition_failed",
                    extra={
                        "user_id": user_id,
                        "concurrent_count": concurrent_count,
                        "max_concurrent": self._config.max_concurrent,
                    },
                )
                return False

            self._user_concurrent[user_id] = concurrent_count + 1
            logger.debug(
                "concurrent_slot_acquired",
                extra={"user_id": user_id, "new_count": self._user_concurrent[user_id]},
            )
            return True

    async def release_concurrent_slot(self, user_id: int) -> None:
        """Release a concurrent operation slot for the user.

        Args:
            user_id: Telegram user ID
        """
        async with self._lock:
            if user_id in self._user_concurrent:
                self._user_concurrent[user_id] = max(0, self._user_concurrent[user_id] - 1)
                if self._user_concurrent[user_id] == 0:
                    del self._user_concurrent[user_id]
                logger.debug(
                    "concurrent_slot_released",
                    extra={"user_id": user_id, "remaining": self._user_concurrent.get(user_id, 0)},
                )

    async def get_user_status(self, user_id: int) -> dict[str, Any]:
        """Get current rate limit status for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            Dictionary with user's current status
        """
        async with self._lock:
            now = time.time()
            user_queue = self._user_requests[user_id]

            # Clean old requests
            cutoff_time = now - self._config.window_seconds
            while user_queue and user_queue[0] < cutoff_time:
                user_queue.popleft()

            cooldown_remaining = 0
            if user_id in self._user_cooldowns:
                cooldown_remaining = max(0, int(self._user_cooldowns[user_id] - now))

            return {
                "user_id": user_id,
                "requests_in_window": len(user_queue),
                "max_requests": self._config.max_requests,
                "window_seconds": self._config.window_seconds,
                "concurrent_operations": self._user_concurrent.get(user_id, 0),
                "max_concurrent": self._config.max_concurrent,
                "cooldown_remaining": cooldown_remaining,
                "is_limited": len(user_queue) >= self._config.max_requests
                or cooldown_remaining > 0,
            }

    async def reset_user(self, user_id: int) -> None:
        """Reset rate limit state for a user (admin function).

        Args:
            user_id: Telegram user ID
        """
        async with self._lock:
            if user_id in self._user_requests:
                del self._user_requests[user_id]
            if user_id in self._user_concurrent:
                del self._user_concurrent[user_id]
            if user_id in self._user_cooldowns:
                del self._user_cooldowns[user_id]
            logger.info("rate_limit_user_reset", extra={"user_id": user_id})

    async def cleanup_expired(self) -> int:
        """Clean up expired entries to prevent memory leaks.

        Returns:
            Number of users cleaned up
        """
        async with self._lock:
            now = time.time()
            cutoff_time = now - self._config.window_seconds
            cleaned_users = 0

            # Clean up request queues
            users_to_remove = []
            for user_id, user_queue in list(self._user_requests.items()):
                while user_queue and user_queue[0] < cutoff_time:
                    user_queue.popleft()
                if not user_queue:
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                del self._user_requests[user_id]
                cleaned_users += 1

            # Clean up expired cooldowns
            expired_cooldowns = [
                user_id
                for user_id, cooldown_until in self._user_cooldowns.items()
                if now >= cooldown_until
            ]
            for user_id in expired_cooldowns:
                del self._user_cooldowns[user_id]

            if cleaned_users > 0:
                logger.debug("rate_limiter_cleanup", extra={"users_cleaned": cleaned_users})

            return cleaned_users
