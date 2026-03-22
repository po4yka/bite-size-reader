"""Edit-oriented flows for response sender."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger
from app.utils.retry_utils import retry_telegram_operation

from ._response_sender_shared import (
    ResponseSenderSharedState,
    normalize_parse_mode,
    validate_and_truncate,
)

logger = get_logger(__name__)


class ResponseSenderEditFlow:
    """Handle edit and edit-or-send flows."""

    def __init__(
        self,
        state: ResponseSenderSharedState,
        *,
        safe_reply_with_id: Any,
    ) -> None:
        self._state = state
        self._safe_reply_with_id = safe_reply_with_id

    async def edit_or_send(
        self,
        message: Any,
        text: str,
        message_id: int | None = None,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
        message_thread_id: int | None = None,
    ) -> int | None:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        if message_id and chat_id:
            edit_success = await self.edit_message(
                chat_id,
                message_id,
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            if edit_success:
                return message_id
            logger.debug(
                "edit_or_send_edit_failed_fallback_send",
                extra={"chat_id": chat_id, "message_id": message_id},
            )

        return await self._safe_reply_with_id(
            message,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
            message_thread_id=message_thread_id,
        )

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> bool:
        text = validate_and_truncate(
            self._state,
            text,
            substitute_on_unsafe=False,
            context_log_key="edit_message",
        )
        if text is None:
            return False

        if not await self._state.validator.check_rate_limit():
            logger.warning(
                "edit_message_rate_limited",
                extra={"chat_id": chat_id, "message_id": message_id},
            )

        self._log_edit_attempt(chat_id, message_id)
        client = self._resolve_edit_client(chat_id, message_id)
        if client is None:
            return False
        if not self._validate_edit_identifiers(chat_id, message_id, text):
            return False

        try:
            return await self._perform_edit_message(
                client,
                chat_id,
                message_id,
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "edit_message_failed",
                exc_info=True,
                extra={"error": str(exc), "chat_id": chat_id, "message_id": message_id},
            )
            return False

    def _log_edit_attempt(self, chat_id: int, message_id: int) -> None:
        logger.debug(
            "edit_message_attempt",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "has_telegram_client": self._state.telegram_client is not None,
                "telegram_client_has_client": (
                    hasattr(self._state.telegram_client, "client")
                    if self._state.telegram_client
                    else False
                ),
                "client": (
                    self._state.telegram_client.client if self._state.telegram_client else None
                ),
            },
        )

    def _resolve_edit_client(self, chat_id: int, message_id: int) -> Any | None:
        if not self._state.telegram_client or not hasattr(self._state.telegram_client, "client"):
            logger.warning(
                "edit_message_no_telegram_client",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return None

        client = self._state.telegram_client.client
        if not client or not hasattr(client, "edit_message_text"):
            logger.warning(
                "edit_message_no_client_method",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return None
        return client

    @staticmethod
    def _validate_edit_identifiers(chat_id: int, message_id: int, text: str) -> bool:
        if isinstance(chat_id, int) and isinstance(message_id, int):
            return True
        logger.warning(
            "edit_message_invalid_params",
            extra={"chat_id": chat_id, "message_id": message_id, "text_length": len(text)},
        )
        return False

    @staticmethod
    def _build_edit_text(text: str, parse_mode: str | None) -> str:
        if parse_mode != "HTML" or "Updated at" in text:
            return text
        now = datetime.now(UTC).strftime("%H:%M:%S")
        return f"{text}\n\n<i>Updated at {now} UTC</i>"

    @staticmethod
    def _is_message_not_modified_error(exc: Exception | None) -> bool:
        if exc is None:
            return False
        exc_str = str(exc).lower()
        return "message is not modified" in exc_str or "message_not_modified" in exc_str

    async def _perform_edit_message(
        self,
        client: Any,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> bool:
        last_error_exc: Exception | None = None

        async def edit() -> None:
            nonlocal last_error_exc
            kwargs: dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": self._build_edit_text(text, parse_mode),
            }
            normalized_mode = normalize_parse_mode(parse_mode)
            if normalized_mode is not None:
                kwargs["parse_mode"] = normalized_mode
            if reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            if disable_web_page_preview is not None:
                kwargs["disable_web_page_preview"] = disable_web_page_preview
            try:
                await client.edit_message_text(**kwargs)
            except Exception as exc:
                raise_if_cancelled(exc)
                last_error_exc = exc
                raise

        _, success = await retry_telegram_operation(edit, operation_name="edit_message")
        if success:
            logger.debug(
                "edit_message_success",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return True

        if self._is_message_not_modified_error(last_error_exc):
            logger.debug(
                "edit_message_not_modified_success",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return True

        logger.warning(
            "edit_message_retry_failed",
            extra={"chat_id": chat_id, "message_id": message_id},
        )
        return False
