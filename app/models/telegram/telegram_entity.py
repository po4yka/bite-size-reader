"""Telegram MessageEntity model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.telegram.telegram_enums import MessageEntityType
from app.models.telegram.telegram_user import TelegramUser


@dataclass
class MessageEntity:
    """Telegram MessageEntity object."""

    type: MessageEntityType
    offset: int
    length: int
    url: str | None = None
    user: TelegramUser | None = None
    language: str | None = None
    custom_emoji_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEntity:
        """Create MessageEntity from dictionary."""
        # Handle entity type conversion more robustly
        entity_type_str = data.get("type", "mention")
        try:
            # Handle both string values and enum objects
            if hasattr(entity_type_str, "value"):
                entity_type_str = entity_type_str.value
            elif hasattr(entity_type_str, "name"):
                entity_type_str = entity_type_str.name.lower()

            # Convert to our enum
            entity_type = MessageEntityType(entity_type_str.lower())
        except (ValueError, AttributeError):
            # Fallback to mention if type is unknown
            entity_type = MessageEntityType.MENTION

        user_data = data.get("user")
        user = TelegramUser.from_dict(user_data) if user_data else None

        return cls(
            type=entity_type,
            offset=data.get("offset", 0),
            length=data.get("length", 0),
            url=data.get("url"),
            user=user,
            language=data.get("language"),
            custom_emoji_id=data.get("custom_emoji_id"),
        )
