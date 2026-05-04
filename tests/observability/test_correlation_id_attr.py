"""Tests for set_correlation_id_attr() — attaches cid to the current span."""

from __future__ import annotations

import pytest

opentelemetry = pytest.importorskip("opentelemetry", reason="opentelemetry SDK not installed")

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.observability.otel as otel_module


def _make_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_cid_attached_to_active_span() -> None:
    """set_correlation_id_attr writes ratatoskr.correlation_id onto the current span."""
    if not otel_module._otel_available:
        pytest.skip("opentelemetry SDK not available")

    provider, exporter = _make_provider()
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("test.root"):
        otel_module.set_correlation_id_attr("cid-abc-xyz-123")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes.get("ratatoskr.correlation_id") == "cid-abc-xyz-123"


def test_cid_not_set_when_no_active_span() -> None:
    """Calling set_correlation_id_attr outside a span must not raise."""
    if not otel_module._otel_available:
        pytest.skip("opentelemetry SDK not available")
    # Outside any span context — span.is_recording() is False → no-op
    otel_module.set_correlation_id_attr("orphan-cid")


def test_cid_noop_for_empty_string() -> None:
    """set_correlation_id_attr is a no-op when cid is falsy."""
    if not otel_module._otel_available:
        pytest.skip("opentelemetry SDK not available")
    provider, exporter = _make_provider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("test.span"):
        otel_module.set_correlation_id_attr("")  # falsy — must not raise or write attr
    spans = exporter.get_finished_spans()
    assert "ratatoskr.correlation_id" not in (spans[0].attributes or {})
