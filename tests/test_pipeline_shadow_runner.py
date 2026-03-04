from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from app.adapters.content.llm_response_workflow import LLMRequestConfig
from app.migration.pipeline_shadow import (
    PipelineShadowRunner,
    build_python_chunk_synthesis_prompt_snapshot_from_input,
    build_python_chunking_preprocess_snapshot_from_input,
    build_python_extraction_adapter_snapshot,
    build_python_summary_aggregate_snapshot_from_input,
    build_python_summary_user_content_snapshot_from_input,
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
async def test_resolve_extraction_adapter_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg())
    expected = build_python_extraction_adapter_snapshot(
        url_hash="hash",
        content_text="Rust pipeline parity keeps Python authoritative.",
        content_source="markdown",
        title="Demo",
        images_count=1,
    )

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command", return_value=expected):
        result = await runner.resolve_extraction_adapter(
            correlation_id="cid",
            request_id=42,
            url_hash="hash",
            content_text="Rust pipeline parity keeps Python authoritative.",
            content_source="markdown",
            title="Demo",
            images_count=1,
        )

    assert result == expected


@pytest.mark.asyncio
async def test_resolve_extraction_adapter_raises_when_rust_fails() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))

    with (
        patch(
            "app.migration.pipeline_shadow.run_rust_shadow_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.pipeline_shadow.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="Python fallback is decommissioned"):
            await runner.resolve_extraction_adapter(
                correlation_id="cid",
                request_id=43,
                url_hash="hash",
                content_text="Rust pipeline parity keeps Python authoritative.",
                content_source="markdown",
                title="Demo",
                images_count=1,
            )

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"
    assert event_call.call_args.kwargs["surface"] == "pipeline_extraction_adapter"


@pytest.mark.asyncio
async def test_resolve_chunking_preprocess_uses_python_when_disabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=False))
    content_text = "x" * 12_000
    enable_chunking = True
    max_chars = 8_000
    long_context_model = "moonshotai/kimi-k2.5"
    payload = {
        "content_text": content_text,
        "enable_chunking": enable_chunking,
        "max_chars": max_chars,
        "long_context_model": long_context_model,
    }
    expected = build_python_chunking_preprocess_snapshot_from_input(payload)

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command") as rust_call:
        result = await runner.resolve_chunking_preprocess(
            correlation_id="cid",
            request_id=1,
            content_text=content_text,
            enable_chunking=enable_chunking,
            max_chars=max_chars,
            long_context_model=long_context_model,
        )

    rust_call.assert_not_called()
    assert result == expected


@pytest.mark.asyncio
async def test_resolve_llm_wrapper_plan_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))
    requests = [
        LLMRequestConfig(
            messages=[{"role": "user", "content": "demo"}],
            response_format={"type": "json_schema"},
            preset_name="schema_strict",
            model_override="base-model",
            max_tokens=1024,
            temperature=0.2,
            top_p=0.9,
        ),
        LLMRequestConfig(
            messages=[{"role": "user", "content": "demo"}],
            response_format={"type": "json_object"},
            preset_name="json_object_guardrail",
            model_override="base-model",
            max_tokens=2048,
            temperature=0.15,
            top_p=0.9,
        ),
    ]
    rust_plan = {
        "request_count": 2,
        "requests": [
            {
                "preset": "schema_strict",
                "model": "base-model",
                "response_type": "json_schema",
                "max_tokens": 1024,
                "temperature": 0.2,
                "top_p": 0.9,
            },
            {
                "preset": "json_object_guardrail",
                "model": "base-model",
                "response_type": "json_object",
                "max_tokens": 2048,
                "temperature": 0.15,
                "top_p": 0.9,
            },
        ],
    }

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value=rust_plan,
    ):
        result = await runner.resolve_llm_wrapper_plan(
            correlation_id="cid",
            request_id=2,
            base_model="base-model",
            requests=requests,
            fallback_models=("fallback-model",),
            flash_model=None,
            flash_fallback_models=(),
        )

    assert result == rust_plan


@pytest.mark.asyncio
async def test_resolve_content_cleaner_uses_python_when_disabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=False))
    raw = "Line one.\n\n### Related Articles\nNav\nNav\nNav\n"

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command") as rust_call:
        result = await runner.resolve_content_cleaner(
            correlation_id="cid",
            request_id=9,
            content_text=raw,
        )

    rust_call.assert_not_called()
    assert "Related Articles" not in result["content_text"]
    assert "Line one." in result["content_text"]


@pytest.mark.asyncio
async def test_resolve_content_cleaner_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))
    rust_payload = {"content_text": "rust-cleaned"}

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value=rust_payload,
    ):
        result = await runner.resolve_content_cleaner(
            correlation_id="cid",
            request_id=10,
            content_text="raw",
        )

    assert result == rust_payload


@pytest.mark.asyncio
async def test_resolve_summary_aggregate_uses_python_when_disabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=False))
    summaries = [
        {"summary_250": "A", "estimated_reading_time_min": 1},
        {"summary_250": "B", "estimated_reading_time_min": 2},
    ]
    expected = build_python_summary_aggregate_snapshot_from_input({"summaries": summaries})

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command") as rust_call:
        result = await runner.resolve_summary_aggregate(
            correlation_id="cid",
            request_id=11,
            summaries=summaries,
        )

    rust_call.assert_not_called()
    assert result == expected


@pytest.mark.asyncio
async def test_resolve_summary_aggregate_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))
    summaries = [{"summary_250": "A"}, {"summary_250": "B"}]
    rust_payload = {"summary_250": "B", "tldr": "B"}

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value=rust_payload,
    ):
        result = await runner.resolve_summary_aggregate(
            correlation_id="cid",
            request_id=12,
            summaries=summaries,
        )

    assert result == rust_payload


@pytest.mark.asyncio
async def test_resolve_chunk_synthesis_prompt_uses_python_when_disabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=False))
    payload: dict[str, Any] = {
        "aggregated": {
            "tldr": "Draft TLDR",
            "summary_250": "Draft summary",
            "key_ideas": ["A", "B"],
        },
        "chosen_lang": "en",
    }
    expected = build_python_chunk_synthesis_prompt_snapshot_from_input(payload)

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command") as rust_call:
        result = await runner.resolve_chunk_synthesis_prompt(
            correlation_id="cid",
            request_id=13,
            aggregated=payload["aggregated"],
            chosen_lang="en",
        )

    rust_call.assert_not_called()
    assert result == expected


@pytest.mark.asyncio
async def test_resolve_chunk_synthesis_prompt_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))
    rust_payload = {"context_text": "ctx", "user_content": "prompt"}

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value=rust_payload,
    ):
        result = await runner.resolve_chunk_synthesis_prompt(
            correlation_id="cid",
            request_id=14,
            aggregated={"summary_250": "draft"},
            chosen_lang="ru",
        )

    assert result == rust_payload


@pytest.mark.asyncio
async def test_resolve_summary_user_content_uses_python_when_disabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=False))
    payload = {
        "content_for_summary": "Breaking: Reuters reported today.",
        "chosen_lang": "ru",
        "search_context": "ctx",
    }
    expected = build_python_summary_user_content_snapshot_from_input(payload)

    with patch("app.migration.pipeline_shadow.run_rust_shadow_command") as rust_call:
        result = await runner.resolve_summary_user_content(
            correlation_id="cid",
            request_id=15,
            content_for_summary=payload["content_for_summary"],
            chosen_lang=payload["chosen_lang"],
            search_context=payload["search_context"],
        )

    rust_call.assert_not_called()
    assert result == expected


@pytest.mark.asyncio
async def test_resolve_summary_user_content_uses_rust_when_enabled() -> None:
    runner = PipelineShadowRunner(_runtime_cfg(migration_shadow_mode_enabled=True))
    rust_payload = {"content_hint": "hint", "user_content": "prompt"}

    with patch(
        "app.migration.pipeline_shadow.run_rust_shadow_command",
        return_value=rust_payload,
    ):
        result = await runner.resolve_summary_user_content(
            correlation_id="cid",
            request_id=16,
            content_for_summary="text",
            chosen_lang="en",
            search_context="",
        )

    assert result == rust_payload
