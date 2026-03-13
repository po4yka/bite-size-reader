"""Rate limiter behavior for Telegram message routing."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
import time

from app.infrastructure.redis import get_redis
from app.security.rate_limiter import RedisUserRateLimiter, UserRateLimiter

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageRouterRateLimiterMixin:
    """Rate limiter selection and lifecycle helpers for MessageRouter."""

    _redis_limiter_available: bool | None

    async def _get_active_rate_limiter(self) -> RedisUserRateLimiter | UserRateLimiter:
        """Get the active rate limiter, preferring Redis when available.

        The get_redis() function handles reconnection internally with rate-limiting,
        so we can safely call it on each request. When Redis was unavailable and
        becomes available again, the limiter will automatically switch to Redis.
        """
        redis_client = await get_redis(self.cfg)

        if redis_client is not None:
            if not self._redis_limiter_available:
                self._redis_limiter = RedisUserRateLimiter(
                    redis_client, self._rate_limiter_config, self.cfg.redis.prefix
                )
                self._redis_limiter_available = True
                logger.info("telegram_rate_limiter_redis_enabled")
            assert self._redis_limiter is not None
            return self._redis_limiter

        if self._redis_limiter_available is True:
            logger.info("telegram_rate_limiter_fallback_to_memory")
        self._redis_limiter_available = False
        return self._rate_limiter

    async def _check_rate_limit(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int, interaction_type: str
    ) -> tuple[bool, str | None]:
        return await limiter.check_and_record(uid, operation=interaction_type)

    async def _acquire_concurrent_slot(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int
    ) -> bool:
        return await limiter.acquire_concurrent_slot(uid)

    async def _release_concurrent_slot(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int
    ) -> None:
        await limiter.release_concurrent_slot(uid)

    async def cleanup_rate_limiter(self) -> int:
        """Clean up expired rate limiter entries to prevent memory leaks.

        Only cleans up the in-memory rate limiter; Redis handles TTL automatically.
        Also cleans up expired notification-suppression and recent message entries.
        Returns the number of users cleaned up.
        """
        cleaned = await self._rate_limiter.cleanup_expired()

        now = time.time()
        expired_notifs = [
            uid for uid, deadline in self._rate_limit_notified_until.items() if now >= deadline
        ]
        for uid in expired_notifs:
            del self._rate_limit_notified_until[uid]

        cutoff = now - self._recent_message_ttl
        expired_msgs = [key for key, (ts, _sig) in self._recent_message_ids.items() if ts < cutoff]
        for key in expired_msgs:
            del self._recent_message_ids[key]

        return cleaned

    def _should_notify_rate_limit(self, uid: int) -> bool:
        now = time.time()
        deadline = self._rate_limit_notified_until.get(uid, 0.0)
        if now >= deadline:
            self._rate_limit_notified_until[uid] = now + self._rate_limit_notice_window
            return True
        logger.debug(
            "rate_limit_notice_suppressed",
            extra={
                "uid": uid,
                "remaining_suppression": max(0.0, deadline - now),
            },
        )
        return False
