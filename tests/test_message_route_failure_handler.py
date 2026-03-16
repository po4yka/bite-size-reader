from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.routing.failure_handler import MessageRouteFailureHandler


@pytest.mark.asyncio
async def test_failure_handler_marks_cancelled_interactions() -> None:
    recorder = SimpleNamespace(update=AsyncMock())
    handler = MessageRouteFailureHandler(
        response_formatter=cast(
            "Any",
            SimpleNamespace(send_error_notification=AsyncMock()),
        ),
        audit_func=lambda *_args, **_kwargs: None,
        interaction_recorder=cast("Any", recorder),
    )

    await handler.handle_cancelled(
        correlation_id="cid-cancel",
        uid=99,
        interaction_id=123,
        start_time=1.0,
    )

    recorder.update.assert_awaited_once_with(
        123,
        response_sent=False,
        response_type="cancelled",
        start_time=1.0,
    )


@pytest.mark.asyncio
async def test_failure_handler_maps_timeout_errors() -> None:
    response_formatter = SimpleNamespace(send_error_notification=AsyncMock())
    recorder = SimpleNamespace(update=AsyncMock())
    handler = MessageRouteFailureHandler(
        response_formatter=cast("Any", response_formatter),
        audit_func=lambda *_args, **_kwargs: None,
        interaction_recorder=cast("Any", recorder),
    )

    await handler.handle_exception(
        message=SimpleNamespace(),
        error=TimeoutError("timeout"),
        correlation_id="cid-timeout",
        interaction_id=55,
        start_time=2.0,
    )

    response_formatter.send_error_notification.assert_awaited_once()
    args = response_formatter.send_error_notification.await_args.args
    assert args[1] == "timeout"
