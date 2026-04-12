from __future__ import annotations

import pytest

from app.observability import metrics


@pytest.mark.skipif(not metrics.PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
def test_aggregation_metrics_are_exported() -> None:
    metrics.record_aggregation_extraction(
        source_kind="threads_post",
        platform="threads",
        outcome="extracted",
        fallback_tier="markdown",
        media_type="mixed",
    )
    metrics.record_aggregation_bundle(
        entrypoint="telegram_message",
        status="partial",
        partial_success=True,
        bundle_profile="multimodal",
        latency_seconds=1.25,
    )
    metrics.record_aggregation_synthesis(
        source_type="mixed",
        bundle_profile="multimodal",
        status="completed",
        used_source_count=2,
        coverage_ratio=1.0,
        cost_usd=0.42,
    )

    exported = metrics.get_metrics().decode("utf-8")

    assert "bsr_aggregation_extraction_total" in exported
    assert 'source_kind="threads_post"' in exported
    assert "bsr_aggregation_bundles_total" in exported
    assert 'bundle_profile="multimodal"' in exported
    assert "bsr_aggregation_synthesis_coverage_ratio_bucket" in exported
    assert "bsr_aggregation_used_sources_bucket" in exported
    assert "bsr_aggregation_cost_usd_total" in exported
