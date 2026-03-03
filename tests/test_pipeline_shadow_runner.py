from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.pipeline_shadow import (
    PipelineShadowRunner,
    build_python_chunking_preprocess_snapshot_from_input,
    build_python_extraction_adapter_snapshot,
    get_shadow_stats_snapshot,
    reset_shadow_stats,
)


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_shadow_mode_enabled": True,
        "migration_shadow_mode_sample_rate": 1.0,
        "migration_shadow_mode_emit_match_logs": False,
        "migration_shadow_mode_timeout_ms": 250,
        "migration_shadow_mode_max_diffs": 8,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_chunking_snapshot_from_input_handles_long_context_bypass() -> None:
    payload = {
        "content_text": "x" * 12_000,
        "enable_chunking": True,
        "max_chars": 8_000,
        "long_context_model": "moonshotai/kimi-k2.5",
    }
    snapshot = build_python_chunking_preprocess_snapshot_from_input(payload)

    assert snapshot["should_chunk"] is False
    assert snapshot["long_context_bypass"] is True
    assert snapshot["estimated_chunk_count"] == 0


@pytest.mark.asyncio
async def test_compare_extraction_adapter_records_match() -> None:
    reset_shadow_stats()
    runner = PipelineShadowRunner(_runtime_cfg())
    expected = build_python_extraction_adapter_snapshot(
        url_hash="hash",
        content_text="Rust pipeline parity keeps Python authoritative.",
        content_source="markdown",
        title="Demo",
        images_count=1,
    )

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command", return_value=expected):
        await runner.compare_extraction_adapter(
            correlation_id="cid",
            request_id=42,
            url_hash="hash",
            content_text="Rust pipeline parity keeps Python authoritative.",
            content_source="markdown",
            title="Demo",
            images_count=1,
        )

    stats = get_shadow_stats_snapshot()["extraction_adapter"]
    assert stats["total"] == 1
    assert stats["matched"] == 1
    assert stats["mismatched"] == 0
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_compare_extraction_adapter_records_mismatch() -> None:
    reset_shadow_stats()
    runner = PipelineShadowRunner(_runtime_cfg())

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value={
            "url_hash": "hash",
            "content_length": 10,
            "word_count": 1,
            "content_source": "markdown",
            "title_present": False,
            "images_count": 0,
            "has_media": False,
            "language_hint": "en",
            "content_fingerprint": "0000000000000000",
            "low_value": True,
        },
    ):
        await runner.compare_extraction_adapter(
            correlation_id="cid",
            request_id=43,
            url_hash="hash",
            content_text="Rust pipeline parity keeps Python authoritative.",
            content_source="markdown",
            title="Demo",
            images_count=1,
        )

    stats = get_shadow_stats_snapshot()["extraction_adapter"]
    assert stats["total"] == 1
    assert stats["matched"] == 0
    assert stats["mismatched"] == 1
