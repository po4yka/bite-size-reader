"""Tests for the /retry Telegram command handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.command_handlers.url_commands_handler import URLCommandsHandler


def _make_ctx(text: str = "/retry abc123", uid: int = 42) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        uid=uid,
        chat_id=0,
        correlation_id="ctx-cid",
        interaction_id=0,
        start_time=0.0,
        message=MagicMock(),
        user_repo=AsyncMock(),
        audit_func=MagicMock(),
        response_formatter=MagicMock(),
    )


def _make_handler(
    *,
    request: dict | None = None,
    url_handler: AsyncMock | None = None,
) -> URLCommandsHandler:
    formatter = MagicMock()
    formatter.safe_reply = AsyncMock()

    request_repo = AsyncMock()
    request_repo.async_get_latest_request_by_correlation_id = AsyncMock(return_value=request)

    provider = MagicMock()
    provider.url_processor = MagicMock()
    url_h = url_handler or AsyncMock()
    url_h.handle_single_url = AsyncMock()
    provider.url_handler = url_h

    return URLCommandsHandler(
        response_formatter=formatter,
        processor_provider=provider,
        request_repo=request_repo,
    )


@pytest.mark.asyncio
async def test_retry_command_rejects_unknown_correlation_id() -> None:
    handler = _make_handler(request=None)
    ctx = _make_ctx("/retry unknown-cid")

    await handler.handle_retry(ctx)

    handler._formatter.safe_reply.assert_awaited_once()
    reply_text = handler._formatter.safe_reply.call_args[0][1]
    assert "No failed request found" in reply_text


@pytest.mark.asyncio
async def test_retry_command_rejects_non_error_status() -> None:
    completed_request = {"user_id": 42, "status": "ok", "input_url": "https://example.com"}
    handler = _make_handler(request=completed_request)
    ctx = _make_ctx("/retry some-cid", uid=42)

    await handler.handle_retry(ctx)

    handler._formatter.safe_reply.assert_awaited_once()
    reply_text = handler._formatter.safe_reply.call_args[0][1]
    assert "ok" in reply_text
    assert "error" in reply_text


@pytest.mark.asyncio
async def test_retry_command_rejects_wrong_user() -> None:
    request_for_other_user = {"user_id": 999, "status": "error", "input_url": "https://x.com"}
    handler = _make_handler(request=request_for_other_user)
    ctx = _make_ctx("/retry cid-x", uid=42)

    await handler.handle_retry(ctx)

    handler._formatter.safe_reply.assert_awaited_once()
    reply_text = handler._formatter.safe_reply.call_args[0][1]
    assert "No failed request found" in reply_text


@pytest.mark.asyncio
async def test_retry_command_invokes_url_handler_with_clone_correlation_id() -> None:
    url_handler = MagicMock()
    url_handler.handle_single_url = AsyncMock()

    failed_request = {
        "user_id": 42,
        "status": "error",
        "input_url": "https://retry.example.com/article",
    }
    handler = _make_handler(request=failed_request, url_handler=url_handler)
    ctx = _make_ctx("/retry cid-orig", uid=42)

    await handler.handle_retry(ctx)

    url_handler.handle_single_url.assert_awaited_once()
    call_kwargs = url_handler.handle_single_url.call_args.kwargs
    assert call_kwargs["url"] == "https://retry.example.com/article"
    assert call_kwargs["correlation_id"] == "cid-orig-retry-1"


@pytest.mark.asyncio
async def test_retry_command_missing_arg_shows_usage() -> None:
    handler = _make_handler()
    ctx = _make_ctx("/retry")

    await handler.handle_retry(ctx)

    handler._formatter.safe_reply.assert_awaited_once()
    reply_text = handler._formatter.safe_reply.call_args[0][1]
    assert "Usage" in reply_text
