"""Tests that _safe_reply and _reply_json propagate asyncio.CancelledError."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from app.adapters.telegram.telegram_bot import TelegramBot


def _make_bot() -> TelegramBot:
    """Create a TelegramBot without triggering __init__ side effects."""
    return TelegramBot.__new__(TelegramBot)


class TestSafeReplyCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_error_propagates(self) -> None:
        """_safe_reply must not swallow CancelledError."""
        bot = _make_bot()
        msg = AsyncMock()
        msg.reply_text = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await bot._safe_reply(msg, "hello")

    async def test_other_exceptions_swallowed(self) -> None:
        """_safe_reply should still swallow non-cancellation exceptions."""
        bot = _make_bot()
        msg = AsyncMock()
        msg.reply_text = AsyncMock(side_effect=RuntimeError("network"))

        # Should not raise
        await bot._safe_reply(msg, "hello")


class TestReplyJsonCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_error_propagates_from_reply_document(self) -> None:
        """_reply_json must not swallow CancelledError from reply_document."""
        bot = _make_bot()
        msg = AsyncMock()
        msg.reply_document = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await bot._reply_json(msg, {"summary_250": "test"})

    async def test_cancelled_error_propagates_from_fallback(self) -> None:
        """_reply_json must not swallow CancelledError in the fallback path."""
        bot = _make_bot()
        msg = AsyncMock()
        # First path fails with a normal exception to trigger fallback
        msg.reply_document = AsyncMock(side_effect=RuntimeError("upload failed"))
        # Fallback path raises CancelledError
        msg.reply_text = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await bot._reply_json(msg, {"summary_250": "test"})

    async def test_other_exceptions_still_handled(self) -> None:
        """_reply_json should still handle non-cancellation exceptions gracefully."""
        bot = _make_bot()
        msg = AsyncMock()
        msg.reply_document = AsyncMock(side_effect=RuntimeError("upload"))
        msg.reply_text = AsyncMock(side_effect=RuntimeError("text too"))

        # Should not raise
        await bot._reply_json(msg, {"summary_250": "test"})


if __name__ == "__main__":
    unittest.main()
