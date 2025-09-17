"""Telegram User model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TelegramUser:
    """Telegram User object."""

    id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    added_to_attachment_menu: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramUser:
        """Create TelegramUser from dictionary."""
        # Ensure ID is always an integer
        user_id = data.get("id", 0)
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        return cls(
            id=user_id,
            is_bot=data.get("is_bot", False),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name"),
            username=data.get("username"),
            language_code=data.get("language_code"),
            is_premium=data.get("is_premium"),
            added_to_attachment_menu=data.get("added_to_attachment_menu"),
        )
