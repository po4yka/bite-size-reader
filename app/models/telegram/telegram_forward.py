"""Telegram ForwardInfo model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.telegram.telegram_chat import TelegramChat


@dataclass
class ForwardInfo:
    """Telegram forward information."""

    from_chat: TelegramChat | None = None
    from_message_id: int | None = None
    signature: str | None = None
    sender_name: str | None = None
    date: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForwardInfo:
        """Create ForwardInfo from dictionary."""
        from_chat_data = data.get("from_chat")
        from_chat = TelegramChat.from_dict(
            from_chat_data) if from_chat_data else None

        return cls(
            from_chat=from_chat,
            from_message_id=data.get("from_message_id"),
            signature=data.get("signature"),
            sender_name=data.get("sender_name"),
            date=data.get("date"),
        )
