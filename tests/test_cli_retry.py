"""Tests for app.cli.retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.cli.retry as retry_module
from app.cli.retry import parse_args, run_retry_cli


@pytest.mark.asyncio
async def test_cli_retry_exits_nonzero_when_request_not_found(tmp_path) -> None:
    args = parse_args(["--correlation-id", "no-such-cid"])
    args.json_path = None

    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "WARNING"

    mock_repo = AsyncMock()
    mock_repo.async_get_latest_request_by_correlation_id = AsyncMock(return_value=None)

    with (
        patch.object(retry_module, "prepare_config", return_value=mock_cfg),
        patch.object(retry_module, "build_runtime_database", return_value=MagicMock()),
        patch.object(retry_module, "build_request_repository", return_value=mock_repo),
        patch.object(retry_module, "setup_json_logging"),
        pytest.raises(SystemExit) as exc_info,
    ):
        await run_retry_cli(args)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_cli_retry_exits_nonzero_when_status_not_error(tmp_path) -> None:
    args = parse_args(["--correlation-id", "pending-cid"])
    args.json_path = None

    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "WARNING"

    pending_request = {
        "status": "pending",
        "input_url": "https://example.com",
        "correlation_id": "pending-cid",
        "user_id": 1,
        "chat_id": 0,
    }
    mock_repo = AsyncMock()
    mock_repo.async_get_latest_request_by_correlation_id = AsyncMock(return_value=pending_request)

    with (
        patch.object(retry_module, "prepare_config", return_value=mock_cfg),
        patch.object(retry_module, "build_runtime_database", return_value=MagicMock()),
        patch.object(retry_module, "build_request_repository", return_value=mock_repo),
        patch.object(retry_module, "setup_json_logging"),
        pytest.raises(SystemExit) as exc_info,
    ):
        await run_retry_cli(args)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_cli_retry_runs_summarize_with_retry_correlation_id(tmp_path) -> None:
    args = parse_args(["--correlation-id", "cid-failed"])
    args.json_path = None

    mock_cfg = MagicMock()
    mock_cfg.runtime.log_level = "WARNING"

    failed_request = {
        "status": "error",
        "input_url": "https://failed.example.com/article",
        "correlation_id": "cid-failed",
        "user_id": 99,
        "chat_id": 100,
    }
    mock_repo = AsyncMock()
    mock_repo.async_get_latest_request_by_correlation_id = AsyncMock(return_value=failed_request)

    handle_summarize = AsyncMock(return_value=(None, False))
    mock_runtime = MagicMock()
    mock_runtime.command_processor.handle_summarize_command = handle_summarize

    close_mock = AsyncMock()

    with (
        patch.object(retry_module, "prepare_config", return_value=mock_cfg),
        patch.object(retry_module, "build_runtime_database", return_value=MagicMock()),
        patch.object(retry_module, "build_request_repository", return_value=mock_repo),
        patch.object(retry_module, "build_summary_cli_runtime", return_value=mock_runtime),
        patch.object(retry_module, "close_runtime_resources", close_mock),
        patch.object(retry_module, "setup_json_logging"),
    ):
        await run_retry_cli(args)

    handle_summarize.assert_awaited_once()
    call_kwargs = handle_summarize.call_args.kwargs
    assert call_kwargs["correlation_id"] == "cid-failed-retry-1"
    assert call_kwargs["uid"] == 99
    assert "https://failed.example.com/article" in call_kwargs["text"]
    close_mock.assert_awaited_once()
