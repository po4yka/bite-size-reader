from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.telegram.draft_stream_sender import DraftStreamSender, DraftStreamSettings


class _MessageStub:
    def __init__(self, chat_id: int = 123, message_id: int = 456) -> None:
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = message_id


@pytest.mark.asyncio
async def test_draft_sender_builds_payload_and_respects_thread_id() -> None:
    telegram_client = SimpleNamespace(client=SimpleNamespace(invoke=AsyncMock()))
    sender = DraftStreamSender(
        telegram_client=telegram_client,
        settings=DraftStreamSettings(
            enabled=True, min_interval_ms=0, min_delta_chars=1, max_chars=64
        ),
    )

    with patch.object(sender, "_send_custom_request", AsyncMock()) as send_custom_request:
        message = _MessageStub()

        result = await sender.send_update(
            message,
            "hello draft",
            message_thread_id=777,
            force=True,
        )

        assert result.ok is True
        send_custom_request.assert_awaited_once_with(
            {"chat_id": 123, "text": "hello draft", "message_thread_id": 777}
        )


@pytest.mark.asyncio
async def test_draft_sender_throttles_small_fast_updates() -> None:
    telegram_client = SimpleNamespace(client=SimpleNamespace(invoke=AsyncMock()))
    sender = DraftStreamSender(
        telegram_client=telegram_client,
        settings=DraftStreamSettings(
            enabled=True, min_interval_ms=10_000, min_delta_chars=100, max_chars=256
        ),
    )

    with patch.object(sender, "_send_custom_request", AsyncMock()) as send_custom_request:
        message = _MessageStub()

        first = await sender.send_update(message, "first", force=False)
        second = await sender.send_update(message, "first plus", force=False)

        assert first.ok is True
        assert first.sent is True
        assert second.ok is True
        assert second.sent is False
        send_custom_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_draft_sender_fallback_is_sticky_per_request() -> None:
    telegram_client = SimpleNamespace(client=SimpleNamespace(invoke=AsyncMock()))
    sender = DraftStreamSender(
        telegram_client=telegram_client,
        settings=DraftStreamSettings(
            enabled=True, min_interval_ms=0, min_delta_chars=1, max_chars=256
        ),
    )

    with patch.object(
        sender,
        "_send_custom_request",
        AsyncMock(side_effect=RuntimeError("unknown method sendMessageDraft")),
    ) as send_custom_request:
        message = _MessageStub()

        first = await sender.send_update(message, "one", force=True)
        second = await sender.send_update(message, "two", force=True)

        assert first.ok is False
        assert first.fallback is True
        assert second.ok is False
        assert second.fallback is True
        assert send_custom_request.await_count == 1
