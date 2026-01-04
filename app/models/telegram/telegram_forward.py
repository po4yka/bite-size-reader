"""Telegram ForwardInfo model."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic needs this at runtime
from typing import Any

from pydantic import BaseModel

from app.models.telegram.telegram_chat import (  # noqa: TC001 - Pydantic needs this at runtime
    TelegramChat,
)


class ForwardInfo(BaseModel):
    """Telegram forward information."""

    from_chat: TelegramChat | None = None
    from_message_id: int | None = None
    signature: str | None = None
    sender_name: str | None = None
    date: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForwardInfo:
        """Create ForwardInfo from dictionary."""
        return cls.model_validate(data)
