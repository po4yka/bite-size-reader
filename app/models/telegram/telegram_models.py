"""Telegram message data models and validation based on official Telegram Bot API.

This module now serves as a central import point for all Telegram models.
Individual models have been split into separate files for better maintainability.
"""

from __future__ import annotations

# Import all model classes from their individual files
from app.models.telegram.telegram_chat import TelegramChat
from app.models.telegram.telegram_entity import MessageEntity
from app.models.telegram.telegram_enums import ChatType, MediaType, MessageEntityType
from app.models.telegram.telegram_forward import ForwardInfo
from app.models.telegram.telegram_message import TelegramMessage
from app.models.telegram.telegram_user import TelegramUser

# Re-export all classes for backward compatibility
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
