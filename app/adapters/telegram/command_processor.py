"""Backward-compatible alias for the Telegram command dispatcher."""

from __future__ import annotations

from app.adapters.telegram.command_dispatcher import (
    CommandDispatchOutcome,
    TelegramCommandDispatcher,
)

CommandProcessor = TelegramCommandDispatcher

__all__ = [
    "CommandDispatchOutcome",
    "CommandProcessor",
    "TelegramCommandDispatcher",
]
