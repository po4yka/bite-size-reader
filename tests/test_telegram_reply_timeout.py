"""Telegram reply methods must time out instead of hanging indefinitely."""

from __future__ import annotations

import asyncio

import pytest


def _make_bot(timeout_sec: float = 0.05):
    from unittest.mock import MagicMock

    from app.adapters.telegram.telegram_bot import TelegramBot

    bot = TelegramBot.__new__(TelegramBot)
    bot.cfg = MagicMock()
    bot.cfg.runtime = MagicMock()
    bot.cfg.runtime.telegram_reply_timeout_sec = timeout_sec
    return bot


@pytest.mark.asyncio
async def test_safe_reply_times_out_instead_of_hanging():
    """_safe_reply should return (not hang) when Telegram API is slow."""
    from unittest.mock import MagicMock

    bot = _make_bot(timeout_sec=0.05)
    msg = MagicMock()

    async def slow_reply(*a, **kw):
        await asyncio.sleep(10)

    msg.reply_text = slow_reply

    # Should return within ~0.1s, not hang for 10s
    await asyncio.wait_for(bot._safe_reply(msg, "test"), timeout=1.0)


@pytest.mark.asyncio
async def test_reply_json_times_out_instead_of_hanging():
    """_reply_json should return (not hang) when Telegram API is slow."""
    from unittest.mock import MagicMock

    bot = _make_bot(timeout_sec=0.05)
    msg = MagicMock()

    async def slow_reply_doc(*a, **kw):
        await asyncio.sleep(10)

    msg.reply_document = slow_reply_doc
    msg.reply_text = slow_reply_doc  # fallback also slow

    await asyncio.wait_for(bot._reply_json(msg, {"key": "value"}), timeout=1.0)


@pytest.mark.asyncio
async def test_safe_reply_cancelled_error_still_propagates():
    """CancelledError must not be swallowed by the timeout wrapper."""
    from unittest.mock import AsyncMock, MagicMock

    bot = _make_bot()
    msg = MagicMock()
    msg.reply_text = AsyncMock(side_effect=asyncio.CancelledError)

    with pytest.raises(asyncio.CancelledError):
        await bot._safe_reply(msg, "test")


@pytest.mark.asyncio
async def test_reply_json_cancelled_error_still_propagates():
    """CancelledError from reply_document must not be swallowed by _reply_json."""
    from unittest.mock import AsyncMock, MagicMock

    bot = _make_bot()
    msg = MagicMock()
    msg.reply_document = AsyncMock(side_effect=asyncio.CancelledError)
    # Fallback should never be reached, but arm it to detect leakage
    msg.reply_text = AsyncMock(side_effect=AssertionError("fallback should not run"))

    with pytest.raises(asyncio.CancelledError):
        await bot._reply_json(msg, {"key": "value"})


@pytest.mark.asyncio
async def test_safe_reply_normal_exception_swallowed():
    """Regular exceptions should still be swallowed (best-effort reply)."""
    from unittest.mock import AsyncMock, MagicMock

    bot = _make_bot()
    msg = MagicMock()
    msg.reply_text = AsyncMock(side_effect=RuntimeError("network error"))

    # Should not raise
    await bot._safe_reply(msg, "test")
