"""Editable progress-message tracker for Reader mode.

Maintains a mapping of (chat_id, trigger_message_id) -> progress_message_id
so that consecutive status updates edit the same Telegram message rather than
sending new ones.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from app.adapters.external.formatting.response_sender import ResponseSenderImpl

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Manages a single editable progress message per incoming request."""

    def __init__(self, response_sender: ResponseSenderImpl) -> None:
        self._response_sender = response_sender
        # (chat_id, trigger_msg_id) -> progress_msg_id
        self._progress_msgs: dict[tuple[int, int], int] = {}

    async def update(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = True,
    ) -> int | None:
        """Send or edit the consolidated progress message for *message*.

        On the first call for a given message, a new reply is sent.
        Subsequent calls edit that same reply in-place.
        """
        try:
            key = self._key(message)
            if key is None:
                # Cannot track -- fall back to plain send
                await self._response_sender.safe_reply(
                    message,
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
                return None

            existing_id = self._progress_msgs.get(key)
            if existing_id is not None:
                chat_id = key[0]
                ok = await self._response_sender.edit_message(
                    chat_id,
                    existing_id,
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
                if ok:
                    return existing_id
                # Edit failed (message deleted?); fall through and send a new one
                logger.debug(
                    "progress_edit_failed_sending_new",
                    extra={"chat_id": chat_id, "message_id": existing_id},
                )

            # Send new progress message and remember its ID
            new_id = await self._response_sender.safe_reply_with_id(
                message,
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            if new_id is not None:
                self._progress_msgs[key] = new_id
            return new_id
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "progress_update_failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "message_id": getattr(message, "id", None),
                },
            )
            return None

    async def finalize(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = True,
    ) -> int | None:
        """Edit the job card into its final *text* and stop tracking it."""
        message_id = await self.update(
            message,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        self.clear(message)
        return message_id

    def clear(self, message: Any) -> None:
        """Stop tracking the progress message for *message*."""
        key = self._key(message)
        if key is not None:
            self._progress_msgs.pop(key, None)

    # ------------------------------------------------------------------
    @staticmethod
    def _key(message: Any) -> tuple[int, int] | None:
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)
        msg_id = getattr(message, "id", None) or getattr(message, "message_id", None)
        if chat_id is not None and msg_id is not None:
            return (int(chat_id), int(msg_id))
        return None
