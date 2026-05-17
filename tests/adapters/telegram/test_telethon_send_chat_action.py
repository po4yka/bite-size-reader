"""Regression tests: TelethonBotClient.send_chat_action must invoke MTProto's
``messages.setTyping`` so the typing indicator actually appears.

The Telethon migration left ``send_chat_action`` unimplemented on the bot-client
wrapper, so the downstream ``_response_sender_reply_flow.send_chat_action``
checked ``hasattr(client, "send_chat_action")`` and silently returned ``False``.
The whole ``TypingIndicator`` infrastructure was wired correctly but never
reached Telegram -- users saw no typing indicator anywhere.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from telethon.tl import functions, types

from app.adapters.telegram.telethon_compat import TelethonBotClient


class _FakeRawClient:
    """Minimal awaitable + ``get_input_entity`` stub for unit tests."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.get_input_entity = AsyncMock(side_effect=lambda peer: f"peer:{peer}")

    async def __call__(self, request: Any) -> None:
        self.calls.append(request)


def _bot_with(fake_client: _FakeRawClient) -> TelethonBotClient:
    bot = TelethonBotClient.__new__(TelethonBotClient)
    bot._client = fake_client
    return bot


@pytest.mark.asyncio
async def test_typing_action_sends_set_typing_with_typing_tl_action() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=555, action="typing")

    assert len(fake.calls) == 1
    request = fake.calls[0]
    assert isinstance(request, functions.messages.SetTypingRequest)
    assert request.peer == "peer:555"
    assert isinstance(request.action, types.SendMessageTypingAction)
    fake.get_input_entity.assert_awaited_once_with(555)


@pytest.mark.asyncio
async def test_default_action_is_typing() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=42)  # no action= -> defaults to typing

    assert isinstance(fake.calls[0].action, types.SendMessageTypingAction)


@pytest.mark.asyncio
async def test_upload_photo_action_carries_progress_field() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=42, action="upload_photo")

    action = fake.calls[0].action
    assert isinstance(action, types.SendMessageUploadPhotoAction)
    assert action.progress == 0


@pytest.mark.asyncio
async def test_record_voice_action_maps_correctly() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=42, action="record_voice")

    assert isinstance(fake.calls[0].action, types.SendMessageRecordAudioAction)


@pytest.mark.asyncio
async def test_unknown_action_defaults_to_typing() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=42, action="something-future-telegram-adds")

    assert isinstance(fake.calls[0].action, types.SendMessageTypingAction)


@pytest.mark.asyncio
async def test_cancel_action_maps_to_cancel_tl_action() -> None:
    fake = _FakeRawClient()
    bot = _bot_with(fake)

    await bot.send_chat_action(chat_id=42, action="cancel")

    assert isinstance(fake.calls[0].action, types.SendMessageCancelAction)
