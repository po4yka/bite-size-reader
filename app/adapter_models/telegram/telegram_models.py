"""Compatibility export for Telegram adapter payload models."""

from __future__ import annotations

from app.models.telegram.telegram_models import (
    ChatType,
    ForwardInfo,
    MediaType,
    MessageEntity,
    MessageEntityType,
    TelegramChat,
    TelegramMessage,
    TelegramUser,
)

__all__ = [
    "ChatType",
    "ForwardInfo",
    "MediaType",
    "MessageEntity",
    "MessageEntityType",
    "TelegramChat",
    "TelegramMessage",
    "TelegramUser",
]
