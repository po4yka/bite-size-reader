"""Unit tests for PerModelCircuitBreaker (Improvement A).

Verifies that each model gets an independent CircuitBreaker instance,
that an open breaker for one model does not affect healthy models, and
that the per-model state tracking mirrors the underlying CircuitBreaker.
"""

from __future__ import annotations

from app.utils.circuit_breaker import CircuitState, PerModelCircuitBreaker


def _open_breaker(cb: PerModelCircuitBreaker, model: str) -> None:
    """Trip the breaker for *model* by recording enough failures."""
    for _ in range(cb.failure_threshold):
        cb.record_failure(model)


def test_per_model_circuit_breaker_independent_states() -> None:
    cb = PerModelCircuitBreaker(failure_threshold=2, timeout=60.0, success_threshold=1)

    _open_breaker(cb, "model/a")

    assert cb.state("model/a") == CircuitState.OPEN
    assert not cb.can_proceed("model/a")
    # model/b is untouched — its breaker must still be CLOSED.
    assert cb.state("model/b") == CircuitState.CLOSED
    assert cb.can_proceed("model/b")


def test_per_model_circuit_breaker_lazy_creation() -> None:
    cb = PerModelCircuitBreaker(failure_threshold=3, timeout=30.0, success_threshold=2)
    # No breakers exist yet.
    assert cb._breakers == {}
    cb.can_proceed("new/model")
    assert "new/model" in cb._breakers


def test_per_model_circuit_breaker_record_success_closes_half_open() -> None:
    import time

    cb = PerModelCircuitBreaker(failure_threshold=1, timeout=0.0, success_threshold=1)
    _open_breaker(cb, "model/x")
    assert cb.state("model/x") == CircuitState.OPEN

    # Advance past timeout so can_proceed transitions to HALF_OPEN.
    # timeout=0.0 means the breaker transitions immediately.
    time.sleep(0.01)
    assert cb.can_proceed("model/x")  # transitions to HALF_OPEN
    assert cb.state("model/x") == CircuitState.HALF_OPEN

    cb.record_success("model/x")
    assert cb.state("model/x") == CircuitState.CLOSED


def test_per_model_circuit_breaker_get_stats_returns_per_model() -> None:
    cb = PerModelCircuitBreaker(failure_threshold=5, timeout=60.0, success_threshold=2)
    cb.record_failure("alpha")
    cb.record_failure("alpha")
    cb.record_success("beta")

    stats_alpha = cb.get_stats("alpha")
    stats_beta = cb.get_stats("beta")

    assert stats_alpha["failure_count"] == 2
    assert stats_alpha["state"] == "closed"
    assert stats_beta["success_count"] == 1
    assert stats_beta["failure_count"] == 0


def test_per_model_circuit_breaker_all_stats() -> None:
    cb = PerModelCircuitBreaker(failure_threshold=5, timeout=60.0, success_threshold=2)
    cb.record_failure("m1")
    cb.record_failure("m2")
    cb.record_failure("m2")

    all_stats = cb.all_stats()
    assert set(all_stats.keys()) == {"m1", "m2"}
    assert all_stats["m1"]["failure_count"] == 1
    assert all_stats["m2"]["failure_count"] == 2
