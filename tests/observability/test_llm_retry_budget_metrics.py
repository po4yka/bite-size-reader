"""Tests for LLM call retry-budget telemetry.

Three new Prometheus signals:
  * llm_call_attempts_total{provider,model,status}     - counter
  * llm_call_retry_exhaustion_total{model}             - counter
  * llm_call_latency_seconds{model}                    - histogram

The tests exercise the public recording functions; if prometheus_client
is unavailable they no-op gracefully.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def metrics_module() -> object:
    # Reimport so each test sees a fresh registry state.
    return importlib.import_module("app.observability.metrics")


class TestLLMCallAttemptsCounter:
    def test_record_attempt_increments_counter(self, metrics_module) -> None:
        if not metrics_module.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client unavailable")
        metric = metrics_module.LLM_CALL_ATTEMPTS_TOTAL
        before = metric.labels(
            provider="openrouter", model="m1", status="success"
        )._value.get()
        metrics_module.record_llm_call_attempt(
            provider="openrouter", model="m1", status="success"
        )
        after = metric.labels(
            provider="openrouter", model="m1", status="success"
        )._value.get()
        assert after == before + 1.0

    def test_record_attempt_error_status(self, metrics_module) -> None:
        if not metrics_module.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client unavailable")
        metric = metrics_module.LLM_CALL_ATTEMPTS_TOTAL
        before = metric.labels(
            provider="openrouter", model="m2", status="error"
        )._value.get()
        metrics_module.record_llm_call_attempt(
            provider="openrouter", model="m2", status="error"
        )
        assert (
            metric.labels(provider="openrouter", model="m2", status="error")._value.get()
            == before + 1.0
        )

    def test_record_attempt_noop_when_prometheus_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, metrics_module
    ) -> None:
        monkeypatch.setattr(metrics_module, "PROMETHEUS_AVAILABLE", False)
        # Must not raise.
        metrics_module.record_llm_call_attempt(
            provider="openrouter", model="x", status="success"
        )


class TestRetryExhaustionCounter:
    def test_record_retry_exhaustion_increments(self, metrics_module) -> None:
        if not metrics_module.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client unavailable")
        metric = metrics_module.LLM_CALL_RETRY_EXHAUSTION_TOTAL
        before = metric.labels(model="m3")._value.get()
        metrics_module.record_llm_call_retry_exhaustion(model="m3")
        assert metric.labels(model="m3")._value.get() == before + 1.0


class TestLLMCallLatencyHistogram:
    def test_record_latency_observes(self, metrics_module) -> None:
        if not metrics_module.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client unavailable")
        metric = metrics_module.LLM_CALL_LATENCY_SECONDS
        # The Histogram _sum tracks total observed value across labels.
        before = metric.labels(model="m4")._sum.get()
        metrics_module.record_llm_call_latency(model="m4", latency_seconds=2.5)
        assert metric.labels(model="m4")._sum.get() == pytest.approx(before + 2.5)

    def test_record_latency_rejects_negative(self, metrics_module) -> None:
        # Defensive: prometheus rejects negative observations, our helper
        # silently drops them so a buggy caller can't crash the request.
        # Must not raise.
        metrics_module.record_llm_call_latency(model="m5", latency_seconds=-1.0)


class TestExposedInMetricsEndpoint:
    def test_metrics_endpoint_includes_new_signals(self, metrics_module) -> None:
        if not metrics_module.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client unavailable")
        metrics_module.record_llm_call_attempt(
            provider="openrouter", model="exposed-test", status="success"
        )
        metrics_module.record_llm_call_retry_exhaustion(model="exposed-test")
        metrics_module.record_llm_call_latency(
            model="exposed-test", latency_seconds=1.0
        )
        payload = metrics_module.get_metrics().decode("utf-8")
        assert "ratatoskr_llm_call_attempts_total" in payload
        assert "ratatoskr_llm_call_retry_exhaustion_total" in payload
        assert "ratatoskr_llm_call_latency_seconds" in payload
