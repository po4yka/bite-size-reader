from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.time_utils import UTC
from app.domain.events.summary_events import SummaryCreated
from app.infrastructure.messaging.handlers.push_notification import PushNotificationEventHandler


def _event() -> SummaryCreated:
    return SummaryCreated(
        occurred_at=dt.datetime(2026, 5, 6, tzinfo=UTC),
        summary_id=100,
        request_id=200,
        language="en",
        has_insights=False,
    )


@pytest.mark.asyncio
async def test_push_notification_body_uses_summary_tldr() -> None:
    push = SimpleNamespace(send_to_user=AsyncMock())
    summary_repo = SimpleNamespace(
        async_get_summary_by_id=AsyncMock(
            return_value={"json_payload": {"tldr": "Short useful summary"}}
        )
    )
    request_repo = SimpleNamespace(
        async_get_request=AsyncMock(
            return_value={"id": 200, "user_id": 1, "input_url": "https://example.com/post"}
        )
    )
    handler = PushNotificationEventHandler(cast("Any", push), summary_repo, request_repo)

    await handler.on_summary_created(_event())

    push.send_to_user.assert_awaited_once_with(
        user_id=1,
        title="Your summary is ready",
        body="Short useful summary",
        data={"summary_id": "100", "type": "summary_ready"},
    )


@pytest.mark.asyncio
async def test_push_notification_body_falls_back_to_domain() -> None:
    push = SimpleNamespace(send_to_user=AsyncMock())
    summary_repo = SimpleNamespace(async_get_summary_by_id=AsyncMock(return_value=None))
    request_repo = SimpleNamespace(
        async_get_request=AsyncMock(
            return_value={"id": 200, "user_id": 1, "normalized_url": "https://example.org/post"}
        )
    )
    handler = PushNotificationEventHandler(cast("Any", push), summary_repo, request_repo)

    await handler.on_summary_created(_event())

    assert push.send_to_user.await_args.kwargs["body"] == "example.org"
