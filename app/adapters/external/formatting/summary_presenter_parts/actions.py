"""Inline action buttons for summary presentation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_action_buttons(summary_id: int | str) -> list[list[dict[str, str]]]:
    summary_id_str = str(summary_id)
    export_row = [
        {"text": "More", "callback_data": f"more:{summary_id_str}"},
        {"text": "PDF", "callback_data": f"export:{summary_id_str}:pdf"},
        {"text": "MD", "callback_data": f"export:{summary_id_str}:md"},
        {"text": "HTML", "callback_data": f"export:{summary_id_str}:html"},
    ]

    action_row = [
        {"text": "Save", "callback_data": f"save:{summary_id_str}"},
        {"text": "Similar", "callback_data": f"similar:{summary_id_str}"},
    ]

    feedback_row = [
        {"text": "👍", "callback_data": f"rate:{summary_id_str}:1"},
        {"text": "👎", "callback_data": f"rate:{summary_id_str}:-1"},
    ]

    return [export_row, action_row, feedback_row]


def create_inline_keyboard(summary_id: int | str) -> Any:
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        summary_id_str = str(summary_id)
        keyboard = [
            [
                InlineKeyboardButton("More", callback_data=f"more:{summary_id_str}"),
                InlineKeyboardButton("PDF", callback_data=f"export:{summary_id_str}:pdf"),
                InlineKeyboardButton("MD", callback_data=f"export:{summary_id_str}:md"),
                InlineKeyboardButton("HTML", callback_data=f"export:{summary_id_str}:html"),
            ],
            [
                InlineKeyboardButton("Save", callback_data=f"save:{summary_id_str}"),
                InlineKeyboardButton("Similar", callback_data=f"similar:{summary_id_str}"),
            ],
            [
                InlineKeyboardButton("👍", callback_data=f"rate:{summary_id_str}:1"),
                InlineKeyboardButton("👎", callback_data=f"rate:{summary_id_str}:-1"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    except ImportError:
        logger.debug("pyrogram_not_available_for_action_buttons")
        return None
    except Exception as exc:
        logger.warning("create_action_buttons_failed", extra={"error": str(exc)})
        return None
