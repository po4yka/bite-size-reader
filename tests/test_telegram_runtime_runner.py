from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.telegram_runtime import TelegramRuntimeRunner


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_telegram_runtime_backend": "python",
        "migration_telegram_runtime_timeout_ms": 150,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_runner_defaults_to_python_backend_when_not_configured() -> None:
    runner = TelegramRuntimeRunner(SimpleNamespace())
    decision = await runner.resolve_command_route(text="/findonline rust")
    assert decision.command == "/find"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_python_backend_routes_aliases() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_backend="python"))
    decision = await runner.resolve_command_route(text="/unread@mybot 5")
    assert decision.command == "/unread"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_rust_backend_uses_rust_runtime_command() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_backend="rust"))
    with patch(
        "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
        return_value={"command": "/find", "handled": True},
    ):
        decision = await runner.resolve_command_route(text="/findonline rust")

    assert decision.command == "/find"
    assert decision.handled is True


@pytest.mark.asyncio
async def test_rust_backend_falls_back_to_python_on_failure_and_records_event() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_backend="rust"))
    with (
        patch(
            "app.migration.telegram_runtime.run_rust_telegram_runtime_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.telegram_runtime.record_cutover_event") as event_call,
    ):
        decision = await runner.resolve_command_route(text="/findonline rust", correlation_id="cid")

    assert decision.command == "/find"
    assert decision.handled is True
    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"
    assert event_call.call_args.kwargs["surface"] == "telegram_runtime_command_route"


@pytest.mark.asyncio
async def test_invalid_backend_value_defaults_to_python() -> None:
    runner = TelegramRuntimeRunner(_runtime_cfg(migration_telegram_runtime_backend="unexpected"))
    decision = await runner.resolve_command_route(text="/start")
    assert decision.command == "/start"
    assert decision.handled is True
