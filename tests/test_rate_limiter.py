"""Tests for rate limiter security module."""

import asyncio
import time
import unittest

from app.security.rate_limiter import RateLimitConfig, UserRateLimiter


class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Test user rate limiter."""

    async def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        limiter = UserRateLimiter(
            RateLimitConfig(max_requests=3, window_seconds=1, max_concurrent=2)
        )

        user_id = 12345

        # First 3 requests should pass
        for i in range(3):
            allowed, msg = await limiter.check_and_record(user_id, operation=f"request_{i}")
            assert allowed, f"Request {i} should be allowed"
            assert msg is None

        # 4th request should be blocked
        allowed, msg = await limiter.check_and_record(user_id, operation="request_4")
        assert not allowed
        assert msg is not None
        assert "Rate limit exceeded" in msg

    async def test_sliding_window(self):
        """Test sliding window behavior."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=2, window_seconds=1))

        user_id = 12345

        # Make 2 requests
        await limiter.check_and_record(user_id)
        await limiter.check_and_record(user_id)

        # 3rd should fail
        allowed, _ = await limiter.check_and_record(user_id)
        assert not allowed

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should work again
        allowed, _ = await limiter.check_and_record(user_id)
        assert allowed

    async def test_default_cooldown_allows_after_window(self):
        """Ensure default cooldown duration matches the sliding window length."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=2, window_seconds=1))

        user_id = 54321

        # Hit the limit quickly
        await limiter.check_and_record(user_id)
        await limiter.check_and_record(user_id)

        allowed, message = await limiter.check_and_record(user_id)
        assert not allowed
        assert message is not None
        assert "Cooldown active for 1 seconds" in message

        # Wait just longer than the configured window/cooldown length
        await asyncio.sleep(1.05)

        allowed, message = await limiter.check_and_record(user_id)
        assert allowed
        assert message is None

    async def test_concurrent_operations(self):
        """Test concurrent operation limiting."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=10, max_concurrent=2))

        user_id = 12345

        # Acquire 2 slots
        assert await limiter.acquire_concurrent_slot(user_id)
        assert await limiter.acquire_concurrent_slot(user_id)

        # 3rd should fail
        assert not await limiter.acquire_concurrent_slot(user_id)

        # Release one slot
        await limiter.release_concurrent_slot(user_id)

        # Should work again
        assert await limiter.acquire_concurrent_slot(user_id)

    async def test_per_user_isolation(self):
        """Test that rate limits are isolated per user."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=2, window_seconds=10))

        user1 = 111
        user2 = 222

        # User 1 makes 2 requests
        await limiter.check_and_record(user1)
        await limiter.check_and_record(user1)

        # User 1 should be limited
        allowed, _ = await limiter.check_and_record(user1)
        assert not allowed

        # User 2 should not be affected
        allowed, _ = await limiter.check_and_record(user2)
        assert allowed

    async def test_cost_based_limiting(self):
        """Test cost-based rate limiting."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=5, window_seconds=10))

        user_id = 12345

        # Request with cost=3
        allowed, _ = await limiter.check_and_record(user_id, cost=3)
        assert allowed

        # Request with cost=2
        allowed, _ = await limiter.check_and_record(user_id, cost=2)
        assert allowed

        # Total is now 5, next request should fail
        allowed, _ = await limiter.check_and_record(user_id, cost=1)
        assert not allowed

    async def test_get_user_status(self):
        """Test getting user status."""
        limiter = UserRateLimiter(
            RateLimitConfig(max_requests=5, window_seconds=10, max_concurrent=3)
        )

        user_id = 12345

        # Make some requests
        await limiter.check_and_record(user_id)
        await limiter.check_and_record(user_id)
        await limiter.acquire_concurrent_slot(user_id)

        status = await limiter.get_user_status(user_id)

        assert status["user_id"] == user_id
        assert status["requests_in_window"] == 2
        assert status["max_requests"] == 5
        assert status["concurrent_operations"] == 1
        assert status["max_concurrent"] == 3
        assert not status["is_limited"]

    async def test_reset_user(self):
        """Test resetting user rate limit state."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=2, window_seconds=10))

        user_id = 12345

        # Exhaust rate limit
        await limiter.check_and_record(user_id)
        await limiter.check_and_record(user_id)
        allowed, _ = await limiter.check_and_record(user_id)
        assert not allowed

        # Reset user
        await limiter.reset_user(user_id)

        # Should work again
        allowed, _ = await limiter.check_and_record(user_id)
        assert allowed

    async def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        limiter = UserRateLimiter(RateLimitConfig(max_requests=5, window_seconds=1))

        # Create requests for multiple users
        await limiter.check_and_record(111)
        await limiter.check_and_record(222)
        await limiter.check_and_record(333)

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Cleanup should remove all users
        cleaned = await limiter.cleanup_expired()
        assert cleaned == 3

    async def test_cooldown_after_limit(self):
        """Test that cooldown is applied after exceeding limit."""
        limiter = UserRateLimiter(
            RateLimitConfig(max_requests=2, window_seconds=1, cooldown_multiplier=2.0)
        )

        user_id = 12345

        # Exhaust limit
        await limiter.check_and_record(user_id)
        await limiter.check_and_record(user_id)

        # Exceed limit
        allowed, msg = await limiter.check_and_record(user_id)
        assert not allowed
        assert "Cooldown active" in msg

        # Wait for window but not cooldown
        await asyncio.sleep(1.1)

        # Should still be in cooldown (2x window = 2 seconds)
        allowed, msg = await limiter.check_and_record(user_id)
        assert not allowed
        assert "cooldown" in msg.lower()


class TestMessageRouterCleanup(unittest.IsolatedAsyncioTestCase):
    """Test message router cleans up notification state."""

    async def test_cleanup_removes_expired_notifications(self):
        """cleanup_rate_limiter should also clean _rate_limit_notified_until."""
        from unittest.mock import MagicMock

        from app.adapters.telegram.message_router import MessageRouter

        cfg = MagicMock()
        cfg.api_limits.requests_limit = 10
        cfg.api_limits.window_seconds = 60
        cfg.api_limits.max_concurrent = 3
        cfg.api_limits.cooldown_multiplier = 1.0

        router = MessageRouter(
            cfg=cfg,
            db=MagicMock(),
            access_controller=MagicMock(),
            command_processor=MagicMock(),
            url_handler=MagicMock(),
            forward_processor=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=MagicMock(),
        )

        now = time.time()
        # Add expired entries (deadline in the past)
        router._rate_limit_notified_until[111] = now - 100
        router._rate_limit_notified_until[222] = now - 50
        # Add active entry (deadline in the future)
        router._rate_limit_notified_until[333] = now + 100

        await router.cleanup_rate_limiter()

        assert 111 not in router._rate_limit_notified_until
        assert 222 not in router._rate_limit_notified_until
        assert 333 in router._rate_limit_notified_until

    async def test_cleanup_removes_expired_recent_messages(self):
        """cleanup_rate_limiter should also clean _recent_message_ids."""
        from unittest.mock import MagicMock

        from app.adapters.telegram.message_router import MessageRouter

        cfg = MagicMock()
        cfg.api_limits.requests_limit = 10
        cfg.api_limits.window_seconds = 60
        cfg.api_limits.max_concurrent = 3
        cfg.api_limits.cooldown_multiplier = 1.0

        router = MessageRouter(
            cfg=cfg,
            db=MagicMock(),
            access_controller=MagicMock(),
            command_processor=MagicMock(),
            url_handler=MagicMock(),
            forward_processor=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=MagicMock(),
        )

        now = time.time()
        # _recent_message_ttl is 120 seconds
        # Add expired entry (timestamp older than TTL)
        router._recent_message_ids[(1, 1, 100)] = (now - 200, "old text")
        # Add active entry (recent timestamp)
        router._recent_message_ids[(1, 1, 200)] = (now - 10, "new text")

        await router.cleanup_rate_limiter()

        assert (1, 1, 100) not in router._recent_message_ids
        assert (1, 1, 200) in router._recent_message_ids


if __name__ == "__main__":
    unittest.main()
