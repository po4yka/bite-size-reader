"""Tests for the app.cli.repository CLI entry point."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cli import repository as repo_cli


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def test_invalid_url_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-GitHub URL should exit with code 2 before touching the DB."""

    async def _run(args: Namespace) -> None:
        await repo_cli.run_repository_cli(args)

    args = Namespace(
        url="https://example.com/not-github",
        user_id=12345,
        json_path=None,
        log_level="INFO",
        env_file=None,
        force_reanalyze=False,
        correlation_id="test-cid",
    )

    # Patch prepare_config so we never touch real env
    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "INFO"
    monkeypatch.setattr(repo_cli, "_prepare_config", lambda _: mock_cfg)

    with pytest.raises(SystemExit) as exc_info:
        import asyncio

        asyncio.run(repo_cli.run_repository_cli(args))

    assert exc_info.value.code == 2


def test_invalid_url_exits_2_via_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns 2 when a non-GitHub URL is supplied."""
    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "INFO"
    monkeypatch.setattr(repo_cli, "_prepare_config", lambda _: mock_cfg)

    rc = repo_cli.main(["--url", "https://not.github.com/foo", "--user-id", "1"])
    assert rc == 2


# ---------------------------------------------------------------------------
# Missing integration
# ---------------------------------------------------------------------------


def test_missing_integration_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no active UserGitHubIntegration exists, exit code must be 3."""
    import asyncio

    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "INFO"
    monkeypatch.setattr(repo_cli, "_prepare_config", lambda _: mock_cfg)

    # Patch build_runtime_database to return a fake DB
    mock_db = MagicMock()

    # Session context manager returns a session whose execute returns None result
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no integration row
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_db.session = MagicMock(return_value=mock_session_ctx)

    monkeypatch.setattr(repo_cli, "build_runtime_database", lambda *a, **kw: mock_db)
    # Patch setup_json_logging to no-op
    monkeypatch.setattr(repo_cli, "setup_json_logging", lambda _: None)

    args = Namespace(
        url="https://github.com/tiangolo/fastapi",
        user_id=99999,
        json_path=None,
        log_level="INFO",
        env_file=None,
        force_reanalyze=False,
        correlation_id="test-cid-missing",
    )

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(repo_cli.run_repository_cli(args))

    assert exc_info.value.code == 3


def test_missing_integration_exits_3_via_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns 3 when the integration row is absent."""
    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "INFO"
    monkeypatch.setattr(repo_cli, "_prepare_config", lambda _: mock_cfg)

    mock_db = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_db.session = MagicMock(return_value=mock_session_ctx)

    monkeypatch.setattr(repo_cli, "build_runtime_database", lambda *a, **kw: mock_db)
    monkeypatch.setattr(repo_cli, "setup_json_logging", lambda _: None)

    rc = repo_cli.main(["--url", "https://github.com/tiangolo/fastapi", "--user-id", "99999"])
    assert rc == 3


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    """Default values are set correctly."""
    args = repo_cli.parse_args(
        ["--url", "https://github.com/owner/repo", "--user-id", "42"]
    )
    assert args.url == "https://github.com/owner/repo"
    assert args.user_id == 42
    assert args.json_path is None
    assert args.log_level == "INFO"
    assert args.force_reanalyze is False
    assert args.correlation_id is None


def test_parse_args_all_flags() -> None:
    """All optional flags are parsed correctly."""
    from pathlib import Path

    args = repo_cli.parse_args(
        [
            "--url", "https://github.com/owner/repo",
            "--user-id", "7",
            "--json-path", "/tmp/out.json",
            "--log-level", "DEBUG",
            "--force-reanalyze",
            "--correlation-id", "abc-123",
        ]
    )
    assert args.json_path == Path("/tmp/out.json")
    assert args.log_level == "DEBUG"
    assert args.force_reanalyze is True
    assert args.correlation_id == "abc-123"


def test_parse_args_url_required() -> None:
    """Missing --url causes SystemExit."""
    with pytest.raises(SystemExit):
        repo_cli.parse_args(["--user-id", "1"])


def test_parse_args_user_id_required() -> None:
    """Missing --user-id causes SystemExit."""
    with pytest.raises(SystemExit):
        repo_cli.parse_args(["--url", "https://github.com/a/b"])


# ---------------------------------------------------------------------------
# main() return codes
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_run_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run(args: Namespace) -> None:
        pass

    monkeypatch.setattr(repo_cli, "run_repository_cli", _fake_run)
    rc = repo_cli.main(["--url", "https://github.com/owner/repo", "--user-id", "1"])
    assert rc == 0


def test_main_returns_one_when_run_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(_args: Namespace) -> None:
        msg = "unexpected failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(repo_cli, "run_repository_cli", _boom)
    rc = repo_cli.main(["--url", "https://github.com/owner/repo", "--user-id", "1"])
    assert rc == 1
