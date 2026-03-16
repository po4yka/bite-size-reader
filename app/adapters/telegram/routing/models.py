"""Typed models used by Telegram routing collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.telegram.telegram_message import TelegramMessage


@dataclass(frozen=True, slots=True)
class PreparedRouteContext:
    """Normalized message context used by router collaborators."""

    message: Any
    telegram_message: TelegramMessage
    text: str
    uid: int
    chat_id: int | None
    message_id: int | None
    has_forward: bool
    forward_from_chat_id: int | None
    forward_from_chat_title: str | None
    forward_from_message_id: int | None
    interaction_type: str
    command: str | None
    first_url: str | None
    media_type: str | None
    correlation_id: str
