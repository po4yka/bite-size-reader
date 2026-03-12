from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.processing_orchestrator import (
    ProcessingOrchestratorRunner,
    build_python_forward_processing_plan,
    build_python_url_processing_plan,
)
from tests.rust_bridge_helpers import ensure_rust_binary

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "migration"
    / "fixtures"
    / "processing_orchestrator"
)
_FIXTURE_INPUT_DIR = _FIXTURE_ROOT / "input"
_FIXTURE_EXPECTED_DIR = _FIXTURE_ROOT / "expected"


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_processing_orchestrator_backend": "python",
        "migration_processing_orchestrator_timeout_ms": 250,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _processing_orchestrator_fixtures() -> list[
    tuple[str, str, dict[str, object], dict[str, object]]
]:
    fixtures: list[tuple[str, str, dict[str, object], dict[str, object]]] = []
    for input_path in sorted(_FIXTURE_INPUT_DIR.glob("*.json")):
        fixture_name = input_path.stem
        envelope = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict):
            msg = f"fixture envelope must be a JSON object: {input_path}"
            raise ValueError(msg)

        fixture_type = str(envelope.get("type") or "").strip()
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            msg = f"fixture payload must be a JSON object: {input_path}"
            raise ValueError(msg)

        expected_path = _FIXTURE_EXPECTED_DIR / f"{fixture_name}.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if not isinstance(expected, dict):
            msg = f"expected fixture must be a JSON object: {expected_path}"
            raise ValueError(msg)

        fixtures.append((fixture_name, fixture_type, payload, expected))

    return fixtures


def test_build_python_url_processing_plan_uses_chunked_strategy_without_long_context() -> None:
    plan = build_python_url_processing_plan(
        {
            "dedupe_hash": "hash",
            "content_text": "Sentence one. Sentence two. Sentence three. " * 4_000,
            "detected_language": "en",
            "preferred_language": "auto",
            "silent": False,
            "enable_chunking": True,
            "configured_chunk_max_chars": 20_000,
            "primary_model": "openrouter/base-model",
            "long_context_model": None,
            "schema_response_type": "json_schema",
            "json_object_response_type": "json_object",
            "max_tokens_schema": 2_048,
            "max_tokens_json_object": 2_048,
            "base_temperature": 0.2,
            "base_top_p": 0.9,
            "json_temperature": 0.15,
            "json_top_p": 0.9,
            "fallback_models": ["openrouter/fallback"],
            "flash_model": None,
            "flash_fallback_models": [],
        }
    )

    assert plan["flow_kind"] == "url"
    assert plan["chosen_lang"] == "en"
    assert plan["summary_strategy"] == "chunked"
    assert isinstance(plan["chunk_plan"], dict)
    assert plan["single_pass_request_plan"] is None


def test_build_python_url_processing_plan_uses_long_context_model_for_single_pass() -> None:
    plan = build_python_url_processing_plan(
        {
            "dedupe_hash": "hash",
            "content_text": "x" * 70_000,
            "detected_language": "en",
            "preferred_language": "ru",
            "silent": False,
            "enable_chunking": True,
            "configured_chunk_max_chars": 20_000,
            "primary_model": "openrouter/base-model",
            "long_context_model": "google/gemini-2.5-pro",
            "schema_response_type": "json_schema",
            "json_object_response_type": "json_object",
            "max_tokens_schema": 2_048,
            "max_tokens_json_object": 2_048,
            "base_temperature": 0.2,
            "base_top_p": 0.9,
            "json_temperature": 0.15,
            "json_top_p": 0.9,
            "fallback_models": ["openrouter/fallback"],
            "flash_model": "google/gemini-3-flash-preview",
            "flash_fallback_models": [],
        }
    )

    assert plan["chosen_lang"] == "ru"
    assert plan["needs_ru_translation"] is False
    assert plan["summary_strategy"] == "single_pass"
    assert plan["summary_model"] == "google/gemini-2.5-pro"
    assert plan["single_pass_request_plan"]["request_count"] >= 2


def test_build_python_forward_processing_plan_builds_channel_prompt_and_truncation_metadata() -> (
    None
):
    plan = build_python_forward_processing_plan(
        {
            "text": "x" * 46_000,
            "source_chat_title": "Channel title",
            "source_user_first_name": None,
            "source_user_last_name": None,
            "forward_sender_name": None,
            "preferred_language": "auto",
            "primary_model": "openrouter/base-model",
        }
    )

    assert plan["flow_kind"] == "forward"
    assert plan["source_label"] == "Channel"
    assert plan["source_title"] == "Channel title"
    assert plan["prompt"].startswith("Channel: Channel title")
    assert plan["llm_prompt_truncated"] is True
    assert "[Content truncated due to length]" in plan["llm_prompt"]


@pytest.mark.asyncio
async def test_resolve_url_processing_plan_uses_rust_when_enabled() -> None:
    runner = ProcessingOrchestratorRunner(
        _runtime_cfg(migration_processing_orchestrator_backend="rust")
    )
    expected = {
        "flow_kind": "url",
        "chosen_lang": "en",
        "summary_strategy": "single_pass",
        "effective_max_chars": 16_000,
    }

    with patch(
        "app.migration.processing_orchestrator.run_rust_processing_orchestrator_command",
        return_value=expected,
    ):
        result = await runner.resolve_url_processing_plan(
            correlation_id="cid",
            request_id=42,
            dedupe_hash="hash",
            content_text="Rust processing plan keeps the shape stable.",
            detected_language="en",
            preferred_language="auto",
            silent=False,
            enable_chunking=True,
            configured_chunk_max_chars=20_000,
            primary_model="openrouter/base-model",
            long_context_model=None,
            schema_response_type="json_schema",
            json_object_response_type="json_object",
            max_tokens_schema=None,
            max_tokens_json_object=None,
            base_temperature=0.2,
            base_top_p=0.9,
            json_temperature=0.15,
            json_top_p=0.9,
            fallback_models=["openrouter/fallback"],
            flash_model=None,
            flash_fallback_models=[],
        )

    assert result == expected


@pytest.mark.asyncio
async def test_resolve_url_processing_plan_raises_when_rust_fails() -> None:
    runner = ProcessingOrchestratorRunner(
        _runtime_cfg(migration_processing_orchestrator_backend="rust")
    )

    with (
        patch(
            "app.migration.processing_orchestrator.run_rust_processing_orchestrator_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.processing_orchestrator.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="Python fallback is disabled"):
            await runner.resolve_url_processing_plan(
                correlation_id="cid",
                request_id=43,
                dedupe_hash="hash",
                content_text="Rust processing plan keeps the shape stable.",
                detected_language="en",
                preferred_language="auto",
                silent=False,
                enable_chunking=True,
                configured_chunk_max_chars=20_000,
                primary_model="openrouter/base-model",
                long_context_model=None,
                schema_response_type="json_schema",
                json_object_response_type="json_object",
                max_tokens_schema=None,
                max_tokens_json_object=None,
                base_temperature=0.2,
                base_top_p=0.9,
                json_temperature=0.15,
                json_top_p=0.9,
                fallback_models=["openrouter/fallback"],
                flash_model=None,
                flash_fallback_models=[],
            )

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["surface"] == "processing_orchestrator_url"


@pytest.mark.asyncio
async def test_processing_orchestrator_runner_executes_real_rust_binary(monkeypatch) -> None:
    binary = ensure_rust_binary(
        binary_name="bsr-processing-orchestrator",
        package_name="bsr-processing-orchestrator",
    )
    monkeypatch.setenv("PROCESSING_ORCHESTRATOR_RUST_BIN", str(binary))
    runner = ProcessingOrchestratorRunner(
        _runtime_cfg(
            migration_processing_orchestrator_backend="rust",
            migration_processing_orchestrator_timeout_ms=2_000,
        )
    )

    result = await runner.resolve_forward_processing_plan(
        correlation_id="cid-real",
        text="Forwarded runtime migration note.",
        source_chat_title="Migration Digest",
        source_user_first_name=None,
        source_user_last_name=None,
        forward_sender_name=None,
        preferred_language="auto",
        primary_model="openrouter/base-model",
    )

    assert result["flow_kind"] == "forward"
    assert result["source_label"] == "Channel"
    assert result["source_title"] == "Migration Digest"
    assert result["prompt"].startswith("Channel: Migration Digest")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "fixture_type", "payload", "expected"),
    _processing_orchestrator_fixtures(),
    ids=[fixture_name for fixture_name, _, _, _ in _processing_orchestrator_fixtures()],
)
async def test_processing_orchestrator_runner_matches_fixture_baselines(
    monkeypatch,
    fixture_name: str,
    fixture_type: str,
    payload: dict[str, object],
    expected: dict[str, object],
) -> None:
    del fixture_name
    binary = ensure_rust_binary(
        binary_name="bsr-processing-orchestrator",
        package_name="bsr-processing-orchestrator",
    )
    monkeypatch.setenv("PROCESSING_ORCHESTRATOR_RUST_BIN", str(binary))
    runner = ProcessingOrchestratorRunner(
        _runtime_cfg(
            migration_processing_orchestrator_backend="rust",
            migration_processing_orchestrator_timeout_ms=2_000,
        )
    )

    if fixture_type == "url_plan":
        actual = await runner.resolve_url_processing_plan(
            correlation_id="fixture-url",
            request_id=101,
            **payload,
        )
    elif fixture_type == "forward_plan":
        actual = await runner.resolve_forward_processing_plan(
            correlation_id="fixture-forward",
            request_id=202,
            **payload,
        )
    else:
        raise AssertionError(f"unsupported fixture type: {fixture_type}")

    assert actual == expected
