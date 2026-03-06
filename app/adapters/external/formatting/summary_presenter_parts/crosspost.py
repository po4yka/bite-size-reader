"""Crosspost summary cards to forum topic threads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import ResponseSender
    from app.adapters.telegram.topic_manager import TopicManager

logger = logging.getLogger(__name__)


async def crosspost_to_topic(
    *,
    topic_manager: TopicManager,
    response_sender: ResponseSender,
    message: Any,
    summary_shaped: dict[str, Any],
    summary_id: int | str | None,
    correlation_id: str | None,
    card_text: str,
    create_keyboard_fn: Any,
) -> None:
    """Send a compact summary card to the matching forum topic thread.

    Silently returns when topic resolution fails or topics are not
    initialized for this chat.
    """
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    if chat_id is None:
        return

    topic_tags = summary_shaped.get("topic_tags") or []
    if not isinstance(topic_tags, list):
        return

    try:
        topic_id = topic_manager.resolve_topic_id(chat_id, topic_tags)
        if topic_id is None:
            return

        keyboard = create_keyboard_fn(summary_id, correlation_id) if summary_id else None
        await response_sender.safe_reply(
            message,
            card_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            message_thread_id=topic_id,
        )
        logger.debug(
            "summary_crossposted_to_topic",
            extra={
                "chat_id": chat_id,
                "topic_id": topic_id,
                "summary_id": summary_id,
                "cid": correlation_id,
            },
        )
    except Exception as exc:
        raise_if_cancelled(exc)
        logger.warning(
            "topic_crosspost_failed",
            extra={
                "chat_id": chat_id,
                "error": str(exc),
                "cid": correlation_id,
            },
        )
