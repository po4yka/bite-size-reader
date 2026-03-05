from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.migration.interface_router import (
    InterfaceRouterRunner,
    build_python_mobile_route_decision,
    build_python_telegram_command_decision,
    rewrite_command_prefix,
)


def _runtime_cfg(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "migration_interface_backend": "rust",
        "migration_interface_timeout_ms": 150,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_python_mobile_route_decision_for_summaries() -> None:
    decision = build_python_mobile_route_decision("GET", "/v1/summaries")
    assert decision.route_key == "summaries"
    assert decision.rate_limit_bucket == "summaries"
    assert decision.requires_auth is True
    assert decision.handled is True


def test_python_mobile_route_decision_for_articles_uses_default_bucket() -> None:
    decision = build_python_mobile_route_decision("GET", "/v1/articles")
    assert decision.route_key == "articles"
    assert decision.rate_limit_bucket == "default"
    assert decision.requires_auth is True
    assert decision.handled is True


def test_python_telegram_command_decision_strips_bot_mention() -> None:
    decision = build_python_telegram_command_decision("/unread@mybot 10")
    assert decision.command == "/unread"
    assert decision.handled is True


def test_python_telegram_command_decision_is_case_sensitive() -> None:
    decision = build_python_telegram_command_decision("/Findonline rust")
    assert decision.command is None
    assert decision.handled is False


def test_python_telegram_command_decision_rejects_leading_whitespace() -> None:
    decision = build_python_telegram_command_decision(" /findonline rust")
    assert decision.command is None
    assert decision.handled is False


def test_rewrite_command_prefix_preserves_arguments() -> None:
    rewritten = rewrite_command_prefix("/findonline rust migration", "/find")
    assert rewritten == "/find rust migration"


def test_runner_defaults_to_rust_backend_when_not_configured() -> None:
    runner = InterfaceRouterRunner(SimpleNamespace())
    assert runner.options.backend == "rust"


@pytest.mark.asyncio
async def test_legacy_backend_modes_are_ignored_and_rust_is_used() -> None:
    runner = InterfaceRouterRunner(_runtime_cfg(migration_interface_backend="python"))
    rust_payload = {
        "route_key": "summaries",
        "rate_limit_bucket": "summaries",
        "requires_auth": True,
        "handled": True,
    }
    with patch(
        "app.migration.interface_router.run_rust_interface_command", return_value=rust_payload
    ):
        decision = await runner.resolve_mobile_route(method="GET", path="/v1/summaries")

    assert decision.route_key == "summaries"
    assert decision.rate_limit_bucket == "summaries"
    assert decision.requires_auth is True


@pytest.mark.asyncio
async def test_rust_mode_raises_on_error_without_python_fallback() -> None:
    runner = InterfaceRouterRunner(_runtime_cfg(migration_interface_backend="rust"))
    with (
        patch(
            "app.migration.interface_router.run_rust_interface_command",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.migration.interface_router.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="Python fallback is decommissioned"):
            await runner.resolve_telegram_command(text="/findonline rust")

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"
    assert event_call.call_args.kwargs["surface"] == "interface_telegram_command"


@pytest.mark.asyncio
async def test_mobile_route_decision_uses_cache_for_repeated_routes() -> None:
    runner = InterfaceRouterRunner(_runtime_cfg())
    rust_payload = {
        "route_key": "summaries",
        "rate_limit_bucket": "summaries",
        "requires_auth": True,
        "handled": True,
    }
    with patch(
        "app.migration.interface_router.run_rust_interface_command",
        return_value=rust_payload,
    ) as rust_call:
        first = await runner.resolve_mobile_route(method="GET", path="/v1/summaries")
        second = await runner.resolve_mobile_route(method="get", path="/v1/summaries")

    assert first.route_key == "summaries"
    assert second.route_key == "summaries"
    assert rust_call.call_count == 1


@pytest.mark.asyncio
async def test_telegram_command_decision_uses_token_cache() -> None:
    runner = InterfaceRouterRunner(_runtime_cfg())
    with patch(
        "app.migration.interface_router.run_rust_interface_command",
        return_value={"command": "/find", "handled": True},
    ) as rust_call:
        first = await runner.resolve_telegram_command(text="/findonline rust migration")
        second = await runner.resolve_telegram_command(text="/findonline another query")

    assert first.command == "/find"
    assert second.command == "/find"
    assert rust_call.call_count == 1
