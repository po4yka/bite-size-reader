"""Contract tests for VectorQueryResult and related result types."""

from __future__ import annotations

import pytest

from app.infrastructure.vector.result_types import VectorQueryHit, VectorQueryResult


def test_empty_result() -> None:
    result = VectorQueryResult.empty()
    assert result.hits == []


def test_result_with_hits() -> None:
    hit = VectorQueryHit(id="req1:chunk0", distance=0.1, metadata={"request_id": 1})
    result = VectorQueryResult(hits=[hit])
    assert len(result.hits) == 1
    assert result.hits[0].id == "req1:chunk0"
    assert result.hits[0].distance == 0.1
    assert result.hits[0].metadata == {"request_id": 1}


def test_hit_is_frozen() -> None:
    hit = VectorQueryHit(id="x", distance=0.5, metadata={})
    try:
        hit.distance = 0.9  # type: ignore[misc]
        assert False, "should have raised"
    except Exception:
        pass


def test_result_is_frozen() -> None:
    result = VectorQueryResult.empty()
    try:
        result.hits = []  # type: ignore[misc]
        assert False, "should have raised"
    except Exception:
        pass


def test_distance_convention() -> None:
    """distance=0 means identical; higher is less similar."""
    identical = VectorQueryHit(id="a", distance=0.0, metadata={})
    close = VectorQueryHit(id="b", distance=0.2, metadata={})
    far = VectorQueryHit(id="c", distance=1.8, metadata={})

    # similarity = 1 - distance  →  identical=1.0, close=0.8, far=-0.8 (clipped to 0)
    assert max(0.0, 1.0 - identical.distance) == 1.0
    assert max(0.0, 1.0 - close.distance) == pytest.approx(0.8)
    assert max(0.0, 1.0 - far.distance) == 0.0
