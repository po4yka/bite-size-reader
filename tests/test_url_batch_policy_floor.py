"""Tests for URLBatchPolicyService floor logic.

Verifies that the adaptive timeout floor prevents the outer per-URL timeout
from firing before the inner LLM cascade finishes.
"""

from __future__ import annotations

import pytest

from app.adapters.telegram.url_batch_policy_service import URLBatchPolicyService


class _FakeEstimate:
    def __init__(self, timeout_sec: float) -> None:
        self.timeout_sec = timeout_sec
        self.source = "combined"
        self.confidence = 0.9


class _FakeAdaptiveService:
    """Minimal stand-in for AdaptiveTimeoutService."""

    enabled = True

    def __init__(self, timeout_sec: float) -> None:
        self._timeout_sec = timeout_sec

    async def get_timeout(self, *, url: str, domain: str) -> _FakeEstimate:
        return _FakeEstimate(self._timeout_sec)


@pytest.mark.asyncio
async def test_floor_applied_when_estimate_below_floor() -> None:
    """When the adaptive estimate is below floor_sec the floor is used instead."""
    per_model_min = 120.0
    num_models = 4  # 1 primary + 3 fallbacks
    scraping_overhead = 60.0
    floor = num_models * per_model_min + scraping_overhead  # 540.0

    policy = URLBatchPolicyService(
        initial_timeout_sec=900.0,
        max_timeout_sec=1800.0,
        floor_sec=floor,
    )

    # Adaptive estimate well below the floor (matches the reported 341s case)
    adaptive_service = _FakeAdaptiveService(timeout_sec=341.0)

    result = await policy.compute_timeout(
        url="https://margaretstorey.com/article",
        attempt=0,
        adaptive_timeout_service=adaptive_service,
    )

    assert result >= floor, (
        f"Expected compute_timeout >= {floor}, got {result}. "
        "Floor was not applied."
    )


@pytest.mark.asyncio
async def test_floor_not_applied_when_estimate_above_floor() -> None:
    """When the adaptive estimate already exceeds floor_sec it passes through unchanged."""
    floor = 540.0
    high_estimate = 700.0

    policy = URLBatchPolicyService(
        initial_timeout_sec=900.0,
        max_timeout_sec=1800.0,
        floor_sec=floor,
    )

    adaptive_service = _FakeAdaptiveService(timeout_sec=high_estimate)

    result = await policy.compute_timeout(
        url="https://example.com/page",
        attempt=0,
        adaptive_timeout_service=adaptive_service,
    )

    # Should use the adaptive estimate, not the floor
    assert result == pytest.approx(high_estimate)


@pytest.mark.asyncio
async def test_no_floor_returns_unmodified_adaptive_estimate() -> None:
    """Without floor_sec set the policy returns the unmodified adaptive estimate (backwards compat)."""
    estimate = 341.0

    policy = URLBatchPolicyService(
        initial_timeout_sec=900.0,
        max_timeout_sec=1800.0,
        # floor_sec intentionally omitted
    )

    adaptive_service = _FakeAdaptiveService(timeout_sec=estimate)

    result = await policy.compute_timeout(
        url="https://margaretstorey.com/article",
        attempt=0,
        adaptive_timeout_service=adaptive_service,
    )

    assert result == pytest.approx(estimate)


@pytest.mark.asyncio
async def test_floor_none_disables_floor() -> None:
    """Passing floor_sec=None explicitly keeps the old behaviour."""
    estimate = 100.0

    policy = URLBatchPolicyService(floor_sec=None)
    adaptive_service = _FakeAdaptiveService(timeout_sec=estimate)

    result = await policy.compute_timeout(
        url="https://example.com/",
        attempt=0,
        adaptive_timeout_service=adaptive_service,
    )

    assert result == pytest.approx(estimate)


@pytest.mark.asyncio
async def test_floor_does_not_exceed_max_timeout() -> None:
    """The floor is still capped by max_timeout_sec."""
    floor = 1600.0

    policy = URLBatchPolicyService(
        initial_timeout_sec=900.0,
        max_timeout_sec=1800.0,
        floor_sec=floor,
    )

    # estimate below floor; floor should be used but is still below max
    adaptive_service = _FakeAdaptiveService(timeout_sec=100.0)

    result = await policy.compute_timeout(
        url="https://example.com/",
        attempt=0,
        adaptive_timeout_service=adaptive_service,
    )

    assert result == pytest.approx(floor)
    assert result <= 1800.0


@pytest.mark.asyncio
async def test_floor_applied_without_adaptive_service() -> None:
    """When no adaptive service is present, initial_timeout_sec is used (floor irrelevant)."""
    policy = URLBatchPolicyService(
        initial_timeout_sec=900.0,
        max_timeout_sec=1800.0,
        floor_sec=540.0,
    )

    # No adaptive service — should fall back to initial_timeout_sec which is already above floor
    result = await policy.compute_timeout(
        url="https://example.com/",
        attempt=0,
        adaptive_timeout_service=None,
    )

    assert result == pytest.approx(900.0)
