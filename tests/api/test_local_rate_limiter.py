"""Tests for the in-memory rate-limit fallback used when Redis is unavailable.

Migrated from three module-level globals (_local_rate_limits,
_local_rate_lock, _local_cleanup_last) plus the `global _local_cleanup_last`
declaration in `_check_local_rate_limit` to a single
LocalRateLimiter class so the `global` keyword can be removed from
app/api/middleware.py (acceptance criterion of
[[eliminate-module-globals]]).
"""

from __future__ import annotations

from app.api.local_rate_limiter import LocalRateLimiter


class TestLocalRateLimiter:
    def test_first_request_is_allowed(self) -> None:
        limiter = LocalRateLimiter()
        allowed, remaining = limiter.check("user-1", limit=5, window=60)
        assert allowed is True
        assert remaining == 4

    def test_exceeds_limit_returns_not_allowed(self) -> None:
        limiter = LocalRateLimiter()
        for _ in range(5):
            allowed, _ = limiter.check("user-2", limit=5, window=60)
            assert allowed is True
        allowed, remaining = limiter.check("user-2", limit=5, window=60)
        assert allowed is False
        assert remaining == 0

    def test_distinct_users_have_independent_buckets(self) -> None:
        limiter = LocalRateLimiter()
        limiter.check("a", limit=1, window=60)
        # b's bucket is independent of a's.
        allowed_b, _ = limiter.check("b", limit=1, window=60)
        assert allowed_b is True

    def test_reset_clears_all_buckets(self) -> None:
        limiter = LocalRateLimiter()
        limiter.check("user-3", limit=1, window=60)
        # Bucket is full.
        allowed, _ = limiter.check("user-3", limit=1, window=60)
        assert allowed is False
        limiter.reset()
        # After reset the bucket is fresh.
        allowed, _ = limiter.check("user-3", limit=1, window=60)
        assert allowed is True


class TestModuleSingleton:
    """The module-level singleton must exist for backward compatibility
    with tests that call .reset() between cases."""

    def test_module_exposes_singleton(self) -> None:
        from app.api import middleware as _mw

        assert hasattr(_mw, "_local_rate_limiter")
        # Singleton type.
        assert isinstance(_mw._local_rate_limiter, LocalRateLimiter)

    def test_global_keyword_no_longer_used_in_middleware(self) -> None:
        # Acceptance criterion of eliminate-module-globals: `rg 'global _'
        # app/api/middleware.py` must report zero usages of the legacy
        # rate-limit globals. We don't grep the entire repo here — that
        # is a separate, broader task — but for *this* slice the
        # _local_cleanup_last global must be gone.
        from pathlib import Path

        src = Path(__file__).parent.parent.parent / "app" / "api" / "middleware.py"
        text = src.read_text(encoding="utf-8")
        assert "global _local_cleanup_last" not in text
