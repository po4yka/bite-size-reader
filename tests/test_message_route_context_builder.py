from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.routing.context_builder import MessageRouteContextBuilder


def _make_builder() -> tuple[MessageRouteContextBuilder, SimpleNamespace]:
    response_formatter = SimpleNamespace(
        safe_reply=AsyncMock(),
        send_error_notification=AsyncMock(),
    )
    builder = MessageRouteContextBuilder(
        response_formatter=cast("Any", response_formatter),
        recent_message_ids={},
        recent_message_ttl=120,
    )
    return builder, response_formatter


def _make_message(**overrides: object) -> SimpleNamespace:
    payload = {
        "id": 42,
        "chat": SimpleNamespace(id=100),
        "from_user": SimpleNamespace(id=7, is_bot=False),
        "text": "hello",
        "caption": None,
        "outgoing": False,
        "forward_from": None,
        "forward_from_chat": None,
        "forward_from_message_id": None,
        "forward_sender_name": None,
        "forward_date": None,
        "document": None,
        "photo": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_prepare_skips_outgoing_messages() -> None:
    builder, formatter = _make_builder()

    context = await builder.prepare(_make_message(outgoing=True), "cid-out")

    assert context is None
    formatter.safe_reply.assert_not_awaited()
    formatter.send_error_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_rejects_oversized_text() -> None:
    builder, formatter = _make_builder()

    context = await builder.prepare(_make_message(text="x" * (50 * 1024 + 1)), "cid-big")

    assert context is None
    formatter.send_error_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_suppresses_duplicate_messages() -> None:
    builder, _formatter = _make_builder()
    message = _make_message(text="same")

    first = await builder.prepare(message, "cid-1")
    second = await builder.prepare(message, "cid-2")

    assert first is not None
    assert second is None
