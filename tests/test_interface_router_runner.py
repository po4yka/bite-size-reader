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
        "migration_interface_backend": "python",
        "migration_interface_sample_rate": 0.0,
        "migration_interface_timeout_ms": 150,
        "migration_interface_emit_match_logs": False,
        "migration_interface_max_diffs": 8,
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


@pytest.mark.asyncio
async def test_canary_mode_uses_rust_for_sampled_mobile_route() -> None:
    runner = InterfaceRouterRunner(
        _runtime_cfg(migration_interface_backend="canary", migration_interface_sample_rate=1.0)
    )
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
async def test_rust_mode_falls_back_to_python_on_error() -> None:
    runner = InterfaceRouterRunner(_runtime_cfg(migration_interface_backend="rust"))
    with patch(
        "app.migration.interface_router.run_rust_interface_command",
        side_effect=RuntimeError("boom"),
    ):
        decision = await runner.resolve_telegram_command(text="/findonline rust")

    assert decision.command == "/find"
    assert decision.handled is True
