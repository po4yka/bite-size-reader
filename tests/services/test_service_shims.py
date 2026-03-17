"""Tests for app/services/ backward-compat re-export shims.

Verifies that each shim module correctly re-exports the expected symbols
from their canonical locations. A broken import here means a shim stopped
working after a refactor — these tests catch that before callers do.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# adaptive_timeout shim
# ---------------------------------------------------------------------------


class TestAdaptiveTimeoutShim:
    def test_exports_adaptive_timeout_service(self) -> None:
        from app.services.adaptive_timeout import AdaptiveTimeoutService

        assert callable(AdaptiveTimeoutService)

    def test_exports_timeout_cache(self) -> None:
        from app.services.adaptive_timeout import TimeoutCache

        assert callable(TimeoutCache)

    def test_exports_timeout_estimate(self) -> None:
        from app.services.adaptive_timeout import TimeoutEstimate

        assert callable(TimeoutEstimate)

    def test_matches_canonical_path(self) -> None:
        from app.application.services.adaptive_timeout import AdaptiveTimeoutService as Canon
        from app.services.adaptive_timeout import AdaptiveTimeoutService as Shim

        assert Shim is Canon


# ---------------------------------------------------------------------------
# digest_subscription_ops shim
# ---------------------------------------------------------------------------


class TestDigestSubscriptionOpsShim:
    def test_exports_subscribe_channel_atomic(self) -> None:
        from app.services.digest_subscription_ops import subscribe_channel_atomic

        assert callable(subscribe_channel_atomic)

    def test_exports_unsubscribe_channel_atomic(self) -> None:
        from app.services.digest_subscription_ops import unsubscribe_channel_atomic

        assert callable(unsubscribe_channel_atomic)

    def test_subscribe_matches_canonical(self) -> None:
        from app.application.services.digest_subscription_ops import (
            subscribe_channel_atomic as canonical_fn,
        )
        from app.services.digest_subscription_ops import (
            subscribe_channel_atomic as shim_fn,
        )

        assert shim_fn is canonical_fn


# ---------------------------------------------------------------------------
# tts_service shim
# ---------------------------------------------------------------------------


class TestTTSServiceShim:
    def test_exports_tts_service(self) -> None:
        from app.services.tts_service import TTSService

        assert callable(TTSService)

    def test_matches_canonical_path(self) -> None:
        from app.application.services.tts_service import TTSService as Canon
        from app.services.tts_service import TTSService as Shim

        assert Shim is Canon


# ---------------------------------------------------------------------------
# scheduler shim  (apscheduler is an optional dep; skip if not installed)
# ---------------------------------------------------------------------------


class TestSchedulerShim:
    def test_exports_scheduler_service(self) -> None:
        pytest = __import__("pytest")
        pytest.importorskip("apscheduler", reason="apscheduler not installed")
        from app.services.scheduler import SchedulerService

        assert callable(SchedulerService)

    def test_matches_canonical_path(self) -> None:
        pytest = __import__("pytest")
        pytest.importorskip("apscheduler", reason="apscheduler not installed")
        from app.application.services.scheduler import SchedulerService as Canon
        from app.services.scheduler import SchedulerService as Shim

        assert Shim is Canon


# ---------------------------------------------------------------------------
# trending_cache shim
# ---------------------------------------------------------------------------


class TestTrendingCacheShim:
    def test_exports_get_trending_payload(self) -> None:
        from app.services.trending_cache import get_trending_payload

        assert callable(get_trending_payload)

    def test_exports_clear_trending_cache(self) -> None:
        from app.services.trending_cache import clear_trending_cache

        assert callable(clear_trending_cache)

    def test_get_matches_canonical_path(self) -> None:
        from app.infrastructure.cache.trending_cache import (
            get_trending_payload as canonical_fn,
        )
        from app.services.trending_cache import get_trending_payload as shim_fn

        assert shim_fn is canonical_fn
