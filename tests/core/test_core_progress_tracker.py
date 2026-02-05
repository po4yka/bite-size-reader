"""Tests for the core ProgressTracker (editable progress messages)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.progress_tracker import ProgressTracker


def _msg(chat_id: int = 100, msg_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), id=msg_id, message_id=msg_id)


class TestProgressTracker(unittest.IsolatedAsyncioTestCase):
    async def test_first_update_sends_new_message(self) -> None:
        sender = MagicMock()
        sender.safe_reply_with_id = AsyncMock(return_value=42)
        sender.edit_message = AsyncMock(return_value=True)
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        await tracker.update(_msg(), "Processing...")

        sender.safe_reply_with_id.assert_awaited_once()
        sender.edit_message.assert_not_awaited()

    async def test_subsequent_update_edits_existing(self) -> None:
        sender = MagicMock()
        sender.safe_reply_with_id = AsyncMock(return_value=42)
        sender.edit_message = AsyncMock(return_value=True)
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        msg = _msg()
        await tracker.update(msg, "Processing...")
        await tracker.update(msg, "Analyzing...")

        sender.safe_reply_with_id.assert_awaited_once()
        sender.edit_message.assert_awaited_once_with(
            100,
            42,
            "Analyzing...",
            parse_mode=None,
            reply_markup=None,
            disable_web_page_preview=True,
        )

    async def test_edit_failure_sends_new_message(self) -> None:
        sender = MagicMock()
        sender.safe_reply_with_id = AsyncMock(side_effect=[42, 43])
        sender.edit_message = AsyncMock(return_value=False)
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        msg = _msg()
        await tracker.update(msg, "First")
        await tracker.update(msg, "Second")

        assert sender.safe_reply_with_id.await_count == 2

    async def test_clear_removes_tracking(self) -> None:
        sender = MagicMock()
        sender.safe_reply_with_id = AsyncMock(return_value=42)
        sender.edit_message = AsyncMock(return_value=True)
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        msg = _msg()
        await tracker.update(msg, "Processing...")
        tracker.clear(msg)
        await tracker.update(msg, "New run...")

        # After clear, should send new message (not edit)
        assert sender.safe_reply_with_id.await_count == 2

    async def test_no_chat_falls_back_to_safe_reply(self) -> None:
        sender = MagicMock()
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        msg = SimpleNamespace()  # no chat/id
        await tracker.update(msg, "fallback")

        sender.safe_reply.assert_awaited_once_with(
            msg,
            "fallback",
            parse_mode=None,
            reply_markup=None,
            disable_web_page_preview=True,
        )

    async def test_clear_on_unknown_message_is_noop(self) -> None:
        sender = MagicMock()
        tracker = ProgressTracker(sender)
        tracker.clear(_msg())  # should not raise

    async def test_safe_reply_with_id_returns_none(self) -> None:
        """When safe_reply_with_id returns None, tracker should not store entry."""
        sender = MagicMock()
        sender.safe_reply_with_id = AsyncMock(return_value=None)
        sender.edit_message = AsyncMock(return_value=True)
        sender.safe_reply = AsyncMock()

        tracker = ProgressTracker(sender)
        msg = _msg()
        await tracker.update(msg, "First")
        await tracker.update(msg, "Second")

        # Both calls should go through safe_reply_with_id (no edit since first returned None)
        assert sender.safe_reply_with_id.await_count == 2
        sender.edit_message.assert_not_awaited()
