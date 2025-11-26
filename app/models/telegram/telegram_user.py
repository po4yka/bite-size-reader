"""Telegram User model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TelegramUser(BaseModel):
    """Telegram User object."""

    id: int = Field(ge=0)
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    added_to_attachment_menu: bool | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, value: Any) -> int:
        """Ensure ID is always an integer."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramUser:
        """Create TelegramUser from dictionary."""
        return cls.model_validate(data)
