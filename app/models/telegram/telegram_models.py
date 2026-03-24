"""Deprecated compatibility export for Telegram adapter payload models."""

from __future__ import annotations

from app.adapter_models.telegram.telegram_models import (
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
