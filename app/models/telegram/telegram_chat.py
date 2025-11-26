"""Telegram Chat model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.telegram.telegram_enums import ChatType


class TelegramChat(BaseModel):
    """Telegram Chat object."""

    id: int = 0
    type: ChatType = ChatType.PRIVATE
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_forum: bool | None = None
    photo: dict[str, Any] | None = None
    active_usernames: list[str] | None = None
    emoji_status_custom_emoji_id: str | None = None
    bio: str | None = None
    has_private_forwards: bool | None = None
    has_restricted_voice_and_video_messages: bool | None = None
    join_to_send_messages: bool | None = None
    join_by_request: bool | None = None
    description: str | None = None
    invite_link: str | None = None
    pinned_message: dict[str, Any] | None = None
    permissions: dict[str, Any] | None = None
    slow_mode_delay: int | None = None
    message_auto_delete_time: int | None = None
    has_aggressive_anti_spam_enabled: bool | None = None
    has_hidden_members: bool | None = None
    has_protected_content: bool | None = None
    sticker_set_name: str | None = None
    can_set_sticker_set: bool | None = None
    linked_chat_id: int | None = None
    location: dict[str, Any] | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, value: Any) -> ChatType:
        """Handle chat type conversion robustly."""
        if isinstance(value, ChatType):
            return value

        try:
            # Handle both string values and enum objects
            if hasattr(value, "value"):
                value = value.value
            elif hasattr(value, "name"):
                value = value.name.lower()

            # Convert to our enum
            return ChatType(str(value).lower())
        except (ValueError, AttributeError):
            # Fallback to private if type is unknown
            return ChatType.PRIVATE

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramChat:
        """Create TelegramChat from dictionary."""
        return cls.model_validate(data)
