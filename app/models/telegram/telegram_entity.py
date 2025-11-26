"""Telegram MessageEntity model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.telegram.telegram_enums import MessageEntityType
from app.models.telegram.telegram_user import TelegramUser


class MessageEntity(BaseModel):
    """Telegram MessageEntity object."""

    type: MessageEntityType = MessageEntityType.MENTION
    offset: int = Field(default=0, ge=0)
    length: int = Field(default=0, ge=0)
    url: str | None = None
    user: TelegramUser | None = None
    language: str | None = None
    custom_emoji_id: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, value: Any) -> MessageEntityType:
        """Handle entity type conversion robustly."""
        if isinstance(value, MessageEntityType):
            return value

        try:
            # Handle both string values and enum objects
            if hasattr(value, "value"):
                value = value.value
            elif hasattr(value, "name"):
                value = value.name.lower()

            # Convert to our enum
            return MessageEntityType(str(value).lower())
        except (ValueError, AttributeError):
            # Fallback to mention if type is unknown
            return MessageEntityType.MENTION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEntity:
        """Create MessageEntity from dictionary."""
        return cls.model_validate(data)
