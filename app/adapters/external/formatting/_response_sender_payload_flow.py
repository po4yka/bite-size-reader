"""Payload and admin-log helpers for response sender."""

from __future__ import annotations

import io
import json
from typing import Any

from app.adapters.telegram.telethon_compat import InlineKeyboardButton, InlineKeyboardMarkup
from app.api.models.responses import success_response
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger

from ._response_sender_shared import ResponseSenderSharedState, build_json_filename

logger = get_logger(__name__)


class ResponseSenderPayloadFlow:
    """Handle JSON replies, inline keyboards, and admin logging."""

    def __init__(self, state: ResponseSenderSharedState, *, safe_reply: Any) -> None:
        self._state = state
        self._safe_reply = safe_reply

    async def reply_json(
        self, message: Any, obj: dict, *, correlation_id: str | None = None, success: bool = True
    ) -> None:
        if success and isinstance(obj, dict) and obj.get("success") in (True, False):
            payload = obj
        elif success:
            payload = success_response(obj, correlation_id=correlation_id)
        else:
            payload = obj

        if self._state.reply_json_func is not None:
            await self._state.reply_json_func(message, payload)
            return

        pretty = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            bio = io.BytesIO(pretty.encode("utf-8"))
            bio.name = build_json_filename(obj)
            msg_any: Any = message
            await msg_any.reply_document(bio, caption="📊 Full Summary JSON attached")
            return
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.error("reply_document_failed", extra={"error": str(exc)})

        await self._safe_reply(message, f"```json\n{pretty}\n```")

    @staticmethod
    def create_inline_keyboard(buttons: list[dict[str, str]]) -> Any:
        try:
            keyboard_buttons = [
                [InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"])]
                for btn in buttons
            ]
            return InlineKeyboardMarkup(keyboard_buttons)
        except Exception as exc:
            logger.error("failed_to_create_inline_keyboard", extra={"error": str(exc)})
            return None

    async def send_to_admin_log(self, text: str, *, correlation_id: str | None = None) -> None:
        if self._state.admin_log_chat_id is None:
            return
        try:
            if correlation_id:
                text = f"[{correlation_id}] {text}"
            client = getattr(self._state.telegram_client, "client", None)
            if client is not None and hasattr(client, "send_message"):
                await client.send_message(chat_id=self._state.admin_log_chat_id, text=text[:4096])
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "admin_log_send_failed", extra={"chat_id": self._state.admin_log_chat_id}
            )
