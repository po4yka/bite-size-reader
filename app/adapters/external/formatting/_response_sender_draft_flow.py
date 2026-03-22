"""Draft-stream flows for response sender."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._response_sender_shared import ResponseSenderSharedState


class ResponseSenderDraftFlow:
    """Handle draft-streaming behavior and fallback."""

    def __init__(
        self,
        state: ResponseSenderSharedState,
        *,
        edit_or_send: Any,
    ) -> None:
        self._state = state
        self._edit_or_send = edit_or_send

    async def send_message_draft(
        self,
        message: Any,
        text: str,
        *,
        message_thread_id: int | None = None,
        force: bool = False,
    ) -> bool:
        result = await self._state.draft_stream_sender.send_update(
            message,
            text,
            message_thread_id=message_thread_id,
            force=force,
        )
        return result.ok

    def clear_message_draft(self, message: Any) -> None:
        self._state.draft_stream_sender.clear(message)

    def is_draft_streaming_enabled(self) -> bool:
        return self._state.draft_stream_sender.enabled

    def set_telegram_client(self, telegram_client: Any) -> None:
        self._state.telegram_client = telegram_client
        self._state.draft_stream_sender.set_telegram_client(telegram_client)

    async def stream_or_edit_message(
        self,
        message: Any,
        text: str,
        *,
        message_id: int | None = None,
        parse_mode: str | None = "HTML",
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
        message_thread_id: int | None = None,
        force_draft: bool = False,
    ) -> int | None:
        draft_ok = await self.send_message_draft(
            message,
            text,
            message_thread_id=message_thread_id,
            force=force_draft,
        )
        if draft_ok:
            return message_id
        return await self._edit_or_send(
            message,
            text,
            message_id=message_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
            message_thread_id=message_thread_id,
        )
