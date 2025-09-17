"""Telegram Chat model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.telegram.telegram_enums import ChatType


@dataclass
class TelegramChat:
    """Telegram Chat object."""

    id: int
    type: ChatType
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramChat:
        """Create TelegramChat from dictionary."""
        # Handle chat type conversion more robustly
        chat_type_str = data.get("type", "private")
        try:
            # Handle both string values and enum objects
            if hasattr(chat_type_str, "value"):
                chat_type_str = chat_type_str.value
            elif hasattr(chat_type_str, "name"):
                chat_type_str = chat_type_str.name.lower()

            # Convert to our enum
            chat_type = ChatType(chat_type_str.lower())
        except (ValueError, AttributeError):
            # Fallback to private if type is unknown
            chat_type = ChatType.PRIVATE

        return cls(
            id=data.get("id", 0),
            type=chat_type,
            title=data.get("title"),
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            is_forum=data.get("is_forum"),
            photo=data.get("photo"),
            active_usernames=data.get("active_usernames"),
            emoji_status_custom_emoji_id=data.get("emoji_status_custom_emoji_id"),
            bio=data.get("bio"),
            has_private_forwards=data.get("has_private_forwards"),
            has_restricted_voice_and_video_messages=data.get(
                "has_restricted_voice_and_video_messages"
            ),
            join_to_send_messages=data.get("join_to_send_messages"),
            join_by_request=data.get("join_by_request"),
            description=data.get("description"),
            invite_link=data.get("invite_link"),
            pinned_message=data.get("pinned_message"),
            permissions=data.get("permissions"),
            slow_mode_delay=data.get("slow_mode_delay"),
            message_auto_delete_time=data.get("message_auto_delete_time"),
            has_aggressive_anti_spam_enabled=data.get("has_aggressive_anti_spam_enabled"),
            has_hidden_members=data.get("has_hidden_members"),
            has_protected_content=data.get("has_protected_content"),
            sticker_set_name=data.get("sticker_set_name"),
            can_set_sticker_set=data.get("can_set_sticker_set"),
            linked_chat_id=data.get("linked_chat_id"),
            location=data.get("location"),
        )
