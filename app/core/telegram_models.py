"""Telegram message data models and validation based on official Telegram Bot API.

This module now serves as a central import point for all Telegram models.
Individual models have been split into separate files for better maintainability.
"""

from __future__ import annotations

# Import all model classes from their individual files
from app.core.telegram_chat import TelegramChat
from app.core.telegram_entity import MessageEntity
from app.core.telegram_enums import ChatType, MediaType, MessageEntityType
from app.core.telegram_forward import ForwardInfo
from app.core.telegram_message import TelegramMessage
from app.core.telegram_user import TelegramUser

# Re-export all classes for backward compatibility
__all__ = [
    "ChatType",
    "MessageEntityType",
    "MediaType",
    "TelegramUser",
    "TelegramChat",
    "MessageEntity",
    "ForwardInfo",
    "TelegramMessage",
]
