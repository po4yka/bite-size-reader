"""Inline keyboard for related reads after summary delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.core.ui_strings import t

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import ResponseSender
    from app.application.services.related_reads_service import RelatedReadItem

logger = get_logger(__name__)

_MAX_TITLE_LEN = 40


def build_related_reads_keyboard(
    items: list[RelatedReadItem],
    lang: str = "en",
) -> Any | None:
    """Build an InlineKeyboardMarkup with one button per related item."""
    if not items:
        return None
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        buttons: list[list[Any]] = []
        for item in items:
            title = item.title
            if len(title) > _MAX_TITLE_LEN:
                title = title[: _MAX_TITLE_LEN - 1] + "\u2026"
            label = f"{title} ({item.age_label})" if item.age_label else title
            buttons.append([InlineKeyboardButton(label, callback_data=f"rel:{item.request_id}")])
        return InlineKeyboardMarkup(buttons)
    except ImportError:
        logger.debug("pyrogram_not_available_for_related_reads")
        return None
    except Exception as exc:
        logger.warning("build_related_reads_keyboard_failed", extra={"error": str(exc)})
        return None


async def send_related_reads(
    response_sender: ResponseSender,
    message: Any,
    items: list[RelatedReadItem],
    lang: str = "en",
) -> None:
    """Send related reads as a separate message with an inline keyboard."""
    if not items:
        return
    keyboard = build_related_reads_keyboard(items, lang)
    if keyboard is None:
        return
    try:
        await response_sender.safe_reply(
            message,
            t("related_header", lang),
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.warning("send_related_reads_failed", extra={"error": str(exc)})
