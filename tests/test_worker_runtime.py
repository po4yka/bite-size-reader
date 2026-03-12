from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.worker_runtime import WorkerRunner


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_worker_backend": "python",
        "migration_worker_timeout_ms": 300000,
        "migration_processing_orchestrator_backend": "python",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_worker_runner_uses_rust_when_enabled() -> None:
    runner = WorkerRunner(_runtime_cfg(migration_worker_backend="rust"))
    expected = {"status": "ok", "summary": {"summary_250": "ok"}, "attempts": []}

    with patch(
        "app.migration.worker_runtime.run_rust_worker_command",
        return_value=expected,
    ) as command_call:
        result = await runner.execute_url_single_pass(
            requests=[
                SimpleNamespace(
                    preset_name="schema_strict",
                    messages=[{"role": "system", "content": "sys"}],
                    response_format={"type": "json_object"},
                    max_tokens=2048,
                    temperature=0.2,
                    top_p=0.9,
                    model_override="primary-model",
                )
            ],
            correlation_id="cid",
            request_id=42,
        )

    assert result == expected
    assert command_call.call_args.args[0] == "url-single-pass"


@pytest.mark.asyncio
async def test_worker_runner_raises_when_rust_fails() -> None:
    runner = WorkerRunner(_runtime_cfg(migration_worker_backend="rust"))

    with (
        patch(
            "app.migration.worker_runtime.run_rust_worker_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.worker_runtime.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="Python fallback is disabled"):
            await runner.execute_forward_text(
                requests=[
                    SimpleNamespace(
                        preset_name=None,
                        messages=[{"role": "system", "content": "sys"}],
                        response_format={"type": "json_object"},
                        max_tokens=2048,
                        temperature=0.2,
                        top_p=0.9,
                        model_override=None,
                    )
                ],
                correlation_id="cid",
                request_id=7,
            )

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["surface"] == "worker_forward_text"


@pytest.mark.asyncio
async def test_worker_runner_executes_chunked_url_when_enabled() -> None:
    runner = WorkerRunner(_runtime_cfg(migration_worker_backend="rust"))
    expected = {
        "status": "ok",
        "summary": {"summary_250": "ok"},
        "attempts": [],
        "chunk_success_count": 2,
        "used_synthesis": True,
    }

    with patch(
        "app.migration.worker_runtime.run_rust_worker_command",
        return_value=expected,
    ) as command_call:
        result = await runner.execute_chunked_url(
            chunk_requests=[
                SimpleNamespace(
                    preset_name="chunk_1",
                    messages=[{"role": "system", "content": "sys"}],
                    response_format={"type": "json_object"},
                    max_tokens=2048,
                    temperature=0.2,
                    top_p=0.9,
                    model_override="primary-model",
                )
            ],
            synthesis_request=SimpleNamespace(
                preset_name="chunk_synthesis",
                response_format={"type": "json_object"},
                max_tokens=4096,
                temperature=0.2,
                top_p=0.9,
                model_override="primary-model",
            ),
            system_prompt="sys",
            chosen_lang="en",
            max_concurrent_calls=3,
            correlation_id="cid",
            request_id=42,
        )

    assert result == expected
    assert command_call.call_args.args[0] == "chunked-url"
    payload = command_call.call_args.args[1]
    assert payload["synthesis"]["system_prompt"] == "sys"
    assert payload["synthesis"]["chosen_lang"] == "en"
    assert payload["max_concurrent_calls"] == 3


def test_worker_runner_warns_when_worker_toggle_is_secondary_to_orchestrator(caplog) -> None:
    with caplog.at_level("WARNING"):
        runner = WorkerRunner(
            _runtime_cfg(
                migration_worker_backend="rust",
                migration_processing_orchestrator_backend="rust",
            )
        )

    assert runner.enabled is True
    assert "migration_worker_backend_is_test_only_when_orchestrator_is_rust" in caplog.text
