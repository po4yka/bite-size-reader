"""Inline action buttons for summary presentation."""

from __future__ import annotations

import logging
from typing import Any

from app.core.ui_strings import t

logger = logging.getLogger(__name__)


def create_action_buttons(summary_id: int | str, lang: str = "en") -> list[list[dict[str, str]]]:
    summary_id_str = str(summary_id)
    export_row = [
        {"text": t("btn_more", lang), "callback_data": f"more:{summary_id_str}"},
        {"text": t("btn_pdf", lang), "callback_data": f"export:{summary_id_str}:pdf"},
        {"text": t("btn_md", lang), "callback_data": f"export:{summary_id_str}:md"},
        {"text": t("btn_html", lang), "callback_data": f"export:{summary_id_str}:html"},
    ]

    action_row = [
        {"text": t("btn_save", lang), "callback_data": f"save:{summary_id_str}"},
        {"text": t("btn_similar", lang), "callback_data": f"similar:{summary_id_str}"},
    ]

    feedback_row = [
        {"text": "+1", "callback_data": f"rate:{summary_id_str}:1"},
        {"text": "-1", "callback_data": f"rate:{summary_id_str}:-1"},
    ]

    return [export_row, action_row, feedback_row]


def create_inline_keyboard(
    summary_id: int | str,
    correlation_id: str | None = None,
    lang: str = "en",
) -> Any:
    try:
        from pyrogram import enums
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        summary_id_str = str(summary_id)
        keyboard = [
            [
                InlineKeyboardButton(
                    t("btn_more", lang),
                    callback_data=f"more:{summary_id_str}",
                    style=enums.ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    t("btn_pdf", lang), callback_data=f"export:{summary_id_str}:pdf"
                ),
                InlineKeyboardButton(
                    t("btn_md", lang), callback_data=f"export:{summary_id_str}:md"
                ),
                InlineKeyboardButton(
                    t("btn_html", lang), callback_data=f"export:{summary_id_str}:html"
                ),
            ],
            [
                InlineKeyboardButton(
                    t("btn_save", lang),
                    callback_data=f"save:{summary_id_str}",
                    style=enums.ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    t("btn_similar", lang), callback_data=f"similar:{summary_id_str}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "+1",
                    callback_data=f"rate:{summary_id_str}:1",
                    style=enums.ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    "-1",
                    callback_data=f"rate:{summary_id_str}:-1",
                    style=enums.ButtonStyle.DANGER,
                ),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    except ImportError:
        logger.debug("pyrogram_not_available_for_action_buttons")
        return None
    except Exception as exc:
        logger.warning(
            "create_action_buttons_failed",
            extra={"error": str(exc), "cid": correlation_id},
        )
        return None
