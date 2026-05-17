"""Unit tests for per-model OpenRouter telemetry helpers (Improvement B).

Verifies that:
- record_per_model_timeout increments the correct counter label.
- record_per_model_latency observes into the correct histogram bucket.
- record_per_model_circuit_breaker_state sets the correct gauge values.

Tests are skipped when prometheus_client is not installed.
"""

from __future__ import annotations

from typing import Any

import pytest

import app.observability.metrics as _metrics_mod

pytestmark = pytest.mark.skipif(
    not _metrics_mod.PROMETHEUS_AVAILABLE,
    reason="prometheus_client not installed",
)


def _counter_value(counter: Any, **labels: Any) -> float:
    return counter.labels(**labels)._value.get()


def _gauge_value(gauge: Any, **labels: Any) -> float:
    return gauge.labels(**labels)._value.get()


def _histogram_count(histogram: Any, **labels: Any) -> float:
    labelled = histogram.labels(**labels)
    for metric in labelled.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return float(sample.value)
    raise AssertionError("histogram count sample not found")


def test_record_per_model_timeout_increments_counter() -> None:
    from app.observability.metrics import OPENROUTER_PER_MODEL_TIMEOUT, record_per_model_timeout

    before = _counter_value(OPENROUTER_PER_MODEL_TIMEOUT, model="test/model-a")
    record_per_model_timeout(model="test/model-a")
    after = _counter_value(OPENROUTER_PER_MODEL_TIMEOUT, model="test/model-a")
    assert after == before + 1.0


def test_record_per_model_timeout_is_noop_without_prometheus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.observability.metrics as m

    monkeypatch.setattr(m, "PROMETHEUS_AVAILABLE", False)
    # Should not raise.
    m.record_per_model_timeout(model="test/noprometheus")


def test_record_per_model_latency_observes_histogram() -> None:
    from app.observability.metrics import OPENROUTER_PER_MODEL_LATENCY, record_per_model_latency

    before_count = _histogram_count(
        OPENROUTER_PER_MODEL_LATENCY, model="test/model-b", outcome="success"
    )
    record_per_model_latency(model="test/model-b", outcome="success", seconds=1.5)
    after_count = _histogram_count(
        OPENROUTER_PER_MODEL_LATENCY, model="test/model-b", outcome="success"
    )
    assert after_count == before_count + 1


def test_record_per_model_latency_is_noop_without_prometheus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.observability.metrics as m

    monkeypatch.setattr(m, "PROMETHEUS_AVAILABLE", False)
    m.record_per_model_latency(model="test/x", outcome="timeout", seconds=99.0)


def test_record_per_model_circuit_breaker_state_sets_active_state_gauge() -> None:
    from app.observability.metrics import (
        OPENROUTER_CIRCUIT_BREAKER_STATE,
        record_per_model_circuit_breaker_state,
    )

    record_per_model_circuit_breaker_state(model="test/model-c", state="open")

    assert _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-c", state="open") == 1.0
    assert (
        _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-c", state="closed") == 0.0
    )
    assert (
        _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-c", state="half_open")
        == 0.0
    )


def test_record_per_model_circuit_breaker_state_transitions() -> None:
    from app.observability.metrics import (
        OPENROUTER_CIRCUIT_BREAKER_STATE,
        record_per_model_circuit_breaker_state,
    )

    record_per_model_circuit_breaker_state(model="test/model-d", state="closed")
    assert (
        _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-d", state="closed") == 1.0
    )

    record_per_model_circuit_breaker_state(model="test/model-d", state="half_open")
    assert (
        _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-d", state="closed") == 0.0
    )
    assert (
        _gauge_value(OPENROUTER_CIRCUIT_BREAKER_STATE, model="test/model-d", state="half_open")
        == 1.0
    )


def test_record_per_model_circuit_breaker_state_is_noop_without_prometheus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.observability.metrics as m

    monkeypatch.setattr(m, "PROMETHEUS_AVAILABLE", False)
    m.record_per_model_circuit_breaker_state(model="test/y", state="open")
