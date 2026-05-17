"""Tests for the latency-aware fallback orderer.

The orderer queries observed P95 latency per model and re-orders the
fallback chain (after the primary, which stays fixed) to minimise
expected wall-clock to first-success. A stickiness factor prevents
thrashing when latencies are similar; cold-start models (no samples)
go to the end.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core.fallback_orderer import FallbackOrderer
from app.infrastructure.persistence.repositories.latency_stats_repository import (
    LatencyStats,
)


@dataclass
class FakeLatencyRepo:
    """Honours the subset of LatencyStatsRepositoryAdapter we touch."""

    stats: dict[str, LatencyStats] = field(default_factory=dict)
    calls: list[tuple[str, int]] = field(default_factory=list)

    async def async_get_model_latency_stats(
        self, model: str, days: int = 7
    ) -> LatencyStats:
        self.calls.append((model, days))
        return self.stats.get(model, LatencyStats(p50_ms=None, p95_ms=None, sample_count=0))


def _stats(p95_ms: float | None, samples: int = 100) -> LatencyStats:
    return LatencyStats(p50_ms=None, p95_ms=p95_ms, sample_count=samples)


@pytest.fixture
def repo() -> FakeLatencyRepo:
    return FakeLatencyRepo()


class TestPrimaryFixed:
    async def test_primary_is_never_reordered(self, repo: FakeLatencyRepo) -> None:
        repo.stats = {
            "primary": _stats(2000),  # slowest
            "alt-a": _stats(100),
            "alt-b": _stats(200),
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        assert result[0] == "primary"


class TestReorderByLatency:
    async def test_sorts_fallbacks_by_p95_ascending(
        self, repo: FakeLatencyRepo
    ) -> None:
        # alt-b is significantly faster than alt-a — well beyond stickiness.
        repo.stats = {
            "primary": _stats(500),
            "alt-a": _stats(2000),
            "alt-b": _stats(200),
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        assert result == ["primary", "alt-b", "alt-a"]


class TestStickinessBias:
    async def test_keeps_configured_order_when_latencies_within_stickiness(
        self, repo: FakeLatencyRepo
    ) -> None:
        # alt-a 600ms vs alt-b 500ms -> ratio 1.2 < 2.0 stickiness -> keep order.
        repo.stats = {
            "primary": _stats(500),
            "alt-a": _stats(600),
            "alt-b": _stats(500),
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        assert result == ["primary", "alt-a", "alt-b"]

    async def test_overrides_order_when_delta_exceeds_stickiness(
        self, repo: FakeLatencyRepo
    ) -> None:
        # 5x delta -> override even with stickiness=2.0
        repo.stats = {
            "primary": _stats(500),
            "alt-a": _stats(5000),
            "alt-b": _stats(500),
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        assert result == ["primary", "alt-b", "alt-a"]


class TestColdStart:
    async def test_unobserved_models_are_appended_last(
        self, repo: FakeLatencyRepo
    ) -> None:
        repo.stats = {
            "alt-a": _stats(200),
            "alt-c": _stats(100),
            # alt-b has no samples
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(
            primary="primary", fallbacks=("alt-a", "alt-b", "alt-c")
        )
        assert result[0] == "primary"
        # alt-b (cold) must be last; alt-c < alt-a (observed) should sort by latency.
        assert result[-1] == "alt-b"
        observed_segment = result[1:-1]
        assert observed_segment == ["alt-c", "alt-a"]

    async def test_insufficient_samples_treated_as_cold(
        self, repo: FakeLatencyRepo
    ) -> None:
        # alt-a has very few samples (< 10) and is not considered "observed".
        repo.stats = {
            "alt-a": LatencyStats(p50_ms=None, p95_ms=10, sample_count=2),
            "alt-b": _stats(1000),
        }
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        # alt-b is observed (slow but real); alt-a is cold and goes after.
        assert result == ["primary", "alt-b", "alt-a"]


class TestCaching:
    async def test_cached_within_ttl_avoids_repo_calls(
        self, repo: FakeLatencyRepo
    ) -> None:
        repo.stats = {"alt-a": _stats(200), "alt-b": _stats(500)}
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0, ttl_seconds=300)
        await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        call_count_after_first = len(repo.calls)
        await orderer.order(primary="primary", fallbacks=("alt-a", "alt-b"))
        # No additional repo calls — cache served the second invocation.
        assert len(repo.calls) == call_count_after_first

    async def test_cache_can_be_invalidated_via_zero_ttl(
        self, repo: FakeLatencyRepo
    ) -> None:
        repo.stats = {"alt-a": _stats(200)}
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0, ttl_seconds=0)
        await orderer.order(primary="primary", fallbacks=("alt-a",))
        n1 = len(repo.calls)
        await orderer.order(primary="primary", fallbacks=("alt-a",))
        assert len(repo.calls) > n1


class TestEdgeCases:
    async def test_empty_fallbacks_returns_primary_only(
        self, repo: FakeLatencyRepo
    ) -> None:
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(primary="primary", fallbacks=())
        assert result == ["primary"]

    async def test_no_repo_returns_original_order(self) -> None:
        # Without a repo, we always keep the configured order — defensive default.
        orderer = FallbackOrderer(repo=None, stickiness_factor=2.0)
        result = await orderer.order(
            primary="primary", fallbacks=("alt-a", "alt-b")
        )
        assert result == ["primary", "alt-a", "alt-b"]

    async def test_primary_deduplicated_from_fallbacks(
        self, repo: FakeLatencyRepo
    ) -> None:
        orderer = FallbackOrderer(repo=repo, stickiness_factor=2.0)
        result = await orderer.order(
            primary="primary", fallbacks=("primary", "alt-a")
        )
        # Primary must not appear twice.
        assert result.count("primary") == 1
        assert "alt-a" in result


class TestConfigDefaults:
    def test_config_exposes_stickiness_factor(self) -> None:
        from app.config.llm import ModelRoutingConfig

        cfg = ModelRoutingConfig()
        assert cfg.latency_stickiness_factor == pytest.approx(2.0)

    def test_config_exposes_cache_ttl(self) -> None:
        from app.config.llm import ModelRoutingConfig

        cfg = ModelRoutingConfig()
        assert cfg.latency_cache_ttl_seconds == pytest.approx(300.0)


class TestErrorIsolation:
    async def test_repo_exception_falls_back_to_configured_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FailingRepo:
            async def async_get_model_latency_stats(
                self, model: str, days: int = 7
            ) -> LatencyStats:
                raise RuntimeError("db down")

        orderer = FallbackOrderer(repo=FailingRepo(), stickiness_factor=2.0)
        result = await orderer.order(
            primary="primary", fallbacks=("alt-a", "alt-b")
        )
        assert result == ["primary", "alt-a", "alt-b"]
