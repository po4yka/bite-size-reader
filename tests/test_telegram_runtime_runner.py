from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.telegram_runtime import TelegramRuntimeRunner
from tests.rust_bridge_helpers import ensure_rust_binary


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_telegram_runtime_timeout_ms": 150,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_runner_defaults_to_rust_backend_when_not_configured() -> None:
    runner = TelegramRuntimeRunner(SimpleNamespace())
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": "/find", "handled": True},
    ):
        decision = await runner.resolve_command_route(text="/findonline rust")
    assert decision.command == "/find"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_rust_backend_uses_rust_runtime_command() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg())
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": "/find", "handled": True},
    ):
        decision = await runner.resolve_command_route(text="/findonline rust")

    assert decision.command == "/find"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_rust_backend_raises_on_failure_without_python_fallback_and_records_event() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg())
    with (
        patch(
            "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.telegram_runtime.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="Python fallback is decommissioned"):
            await runner.resolve_command_route(text="/findonline rust", correlation_id="cid")

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"
    assert event_call.call_args.kwargs["surface"] == "telegram_runtime_command_route"


@pytest.mark.asyncio
async def test_legacy_backend_toggle_is_ignored_with_warning() -> None:
    with patch("app.migration.telegram_runtime.logger.warning") as warn_call:
        runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_backend="python"))

    warn_call.assert_called_once()
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": "/start", "handled": True},
    ):
        decision = await runner.resolve_command_route(text="/start")
    assert decision.command == "/start"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_command_route_uses_cache_for_same_command_token() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg())
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": "/find", "handled": True},
    ) as rust_call:
        first = await runner.resolve_command_route(text="/findonline rust migration")
        second = await runner.resolve_command_route(text="/findonline another query")

    assert first.command == "/find"
    assert second.command == "/find"
    assert rust_call.call_count == 1


@pytest.mark.asyncio
async def test_command_route_uses_shared_non_command_cache_bucket() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg())
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": None, "handled": False},
    ) as rust_call:
        first = await runner.resolve_command_route(text="hello")
        second = await runner.resolve_command_route(text="world")

    assert first.handled is False
    assert second.handled is False
    assert rust_call.call_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_telegram_runtime_runner_executes_real_rust_binary(monkeypatch) -> None:
    binary = ensure_rust_binary("bsr-telegram-runtime", "bsr-telegram-runtime")
    monkeypatch.setenv("TELEGRAM_RUNTIME_RUST_BIN", str(binary))

    runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_timeout_ms=2_000))
    decision = await runner.resolve_command_route(text="/findonline rust migration")

    assert decision.command == "/find"
    assert decision.handled is True
