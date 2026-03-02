"""Core Telegram message sending."""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.api.models.responses import success_response
from app.core.async_utils import raise_if_cancelled
from app.utils.retry_utils import retry_telegram_operation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.formatting.message_validator import MessageValidatorImpl

logger = logging.getLogger(__name__)


def _normalize_parse_mode(mode: str | None) -> Any:
    """Convert string parse mode to Pyrogram enum.

    Pyrogram 2.x requires enums.ParseMode, not string literals.
    This helper allows callers to use "HTML" or "MARKDOWN" strings
    while ensuring Pyrogram receives the correct enum value.
    """
    if mode is None:
        return None
    # Already an enum or non-string type -- return as-is
    if not isinstance(mode, str):
        return mode
    try:
        from pyrogram import enums

        mode_upper = mode.upper()
        if mode_upper == "HTML":
            return enums.ParseMode.HTML
        if mode_upper in ("MARKDOWN", "MD"):
            return enums.ParseMode.MARKDOWN
        if mode_upper == "DISABLED":
            return enums.ParseMode.DISABLED
        # Unknown string value -- return as-is
        return mode
    except ImportError:
        # Pyrogram not available, return as-is
        return mode


class ResponseSenderImpl:
    """Implementation of core Telegram message sending."""

    def __init__(
        self,
        validator: MessageValidatorImpl,
        *,
        max_message_chars: int = 3500,
        safe_reply_func: Callable[[Any, str], Awaitable[None]] | None = None,
        reply_json_func: Callable[[Any, dict], Awaitable[None]] | None = None,
        telegram_client: Any = None,
        admin_log_chat_id: int | None = None,
    ) -> None:
        """Initialize the response sender.

        Args:
            validator: Message validator for security checks.
            max_message_chars: Maximum characters per message.
            safe_reply_func: Optional callback for test compatibility.
            reply_json_func: Optional callback for test compatibility.
            telegram_client: Optional Telegram client for message operations.
            admin_log_chat_id: Optional chat ID for admin-level debug logging.
        """
        self._validator = validator
        self._max_message_chars = max_message_chars
        self._safe_reply_func = safe_reply_func
        self._reply_json_func = reply_json_func
        self._telegram_client = telegram_client
        self._admin_log_chat_id = admin_log_chat_id

    async def safe_reply(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any = None,
        disable_web_page_preview: bool | None = None,
        message_thread_id: int | None = None,
    ) -> None:
        """Safely reply to a message with comprehensive security checks."""
        # Input validation
        if not text or not text.strip():
            logger.warning("safe_reply_empty_text", extra={"parse_mode": parse_mode is not None})
            return

        # Security content check
        is_safe, error_msg = self._validator.is_safe_content(text)
        if not is_safe:
            logger.warning(
                "safe_reply_unsafe_content_blocked",
                extra={"error": error_msg, "text_length": len(text), "text_preview": text[:100]},
            )
            # Send safe error message instead
            safe_text = "❌ Message blocked for security reasons."
            text = safe_text

        # Length check
        if len(text) > self._max_message_chars:
            logger.warning(
                "safe_reply_message_too_long",
                extra={"length": len(text), "max": self._max_message_chars},
            )
            # Truncate if too long
            text = text[: self._max_message_chars - 10] + "..."

        # Rate limiting check
        if not await self._validator.check_rate_limit():
            logger.warning("safe_reply_rate_limited", extra={"text_length": len(text)})

        if self._safe_reply_func is not None:
            kwargs: dict[str, Any] = {}
            if parse_mode is not None:
                kwargs["parse_mode"] = parse_mode
            if reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            await self._safe_reply_func(message, text, **kwargs)
            return

        try:
            msg_any: Any = message

            # Define send operation for retry logic
            async def do_send() -> Any:
                kwargs: dict[str, Any] = {}
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                if reply_markup:
                    kwargs["reply_markup"] = reply_markup
                if disable_web_page_preview is not None:
                    kwargs["disable_web_page_preview"] = disable_web_page_preview

                # When message_thread_id is set, send to a specific forum topic
                # thread using client.send_message() instead of reply_text().
                if message_thread_id is not None and self._telegram_client is not None:
                    client = getattr(self._telegram_client, "client", None)
                    chat_id = getattr(getattr(msg_any, "chat", None), "id", None)
                    if client is not None and chat_id is not None:
                        kwargs["message_thread_id"] = message_thread_id
                        return await client.send_message(chat_id, text, **kwargs)

                return await msg_any.reply_text(text, **kwargs)

            # Retry the send operation with exponential backoff
            _, success = await retry_telegram_operation(do_send, operation_name="safe_reply")

            if success:
                logger.debug(
                    "reply_text_sent",
                    extra={"length": len(text), "has_buttons": reply_markup is not None},
                )
            else:
                logger.warning(
                    "safe_reply_retry_failed",
                    extra={"text_length": len(text)},
                )
        except Exception as e:
            raise_if_cancelled(e)
            logger.error(
                "reply_failed",
                exc_info=True,
                extra={"error": str(e), "text_length": len(text)},
            )

    def _prepare_text_for_reply_with_id(self, text: str, parse_mode: str | None) -> str | None:
        """Validate and normalize text used by safe_reply_with_id."""
        if not text or not text.strip():
            logger.warning(
                "safe_reply_with_id_empty_text",
                extra={"parse_mode": parse_mode is not None},
            )
            return None

        is_safe, error_msg = self._validator.is_safe_content(text)
        if not is_safe:
            logger.warning(
                "safe_reply_with_id_unsafe_content_blocked",
                extra={"error": error_msg, "text_length": len(text), "text_preview": text[:100]},
            )
            text = "❌ Message blocked for security reasons."

        if len(text) > self._max_message_chars:
            logger.warning(
                "safe_reply_with_id_message_too_long",
                extra={"length": len(text), "max": self._max_message_chars},
            )
            text = text[: self._max_message_chars - 10] + "..."
        return text

    @staticmethod
    def _build_message_kwargs(
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> dict[str, Any]:
        """Build optional kwargs for Telegram send/edit methods."""
        kwargs: dict[str, Any] = {}
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            kwargs["disable_web_page_preview"] = disable_web_page_preview
        return kwargs

    @staticmethod
    def _extract_message_id(sent_message: Any) -> int | None:
        """Extract a Telegram message ID from API response object."""
        message_id = getattr(sent_message, "message_id", None)
        if message_id is None:
            message_id = getattr(sent_message, "id", None)
        return message_id

    async def _send_via_client_with_id(
        self,
        client: Any,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> int | None:
        """Send using Telegram client.send_message and return message ID."""

        async def do_send() -> Any:
            kwargs = {"chat_id": chat_id, "text": text}
            kwargs.update(
                self._build_message_kwargs(
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
            )
            return await client.send_message(**kwargs)

        sent, success = await retry_telegram_operation(
            do_send, operation_name="send_message_with_id"
        )
        if not success or sent is None:
            logger.warning(
                "reply_with_id_retry_failed",
                extra={"chat_id": chat_id, "text_length": len(text)},
            )
            return None

        message_id = self._extract_message_id(sent)
        logger.debug(
            "reply_with_id_result",
            extra={"message_id": message_id, "sent_message_type": type(sent).__name__},
        )
        return message_id

    async def _invoke_safe_reply_callback(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> None:
        """Invoke compatibility reply callback and handle older signatures."""
        if self._safe_reply_func is None:
            return
        kwargs = self._build_message_kwargs(
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        try:
            await self._safe_reply_func(message, text, **kwargs)
        except TypeError:
            kwargs.pop("reply_markup", None)
            kwargs.pop("disable_web_page_preview", None)
            await self._safe_reply_func(message, text, **kwargs)

    async def _reply_text_with_id(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> int | None:
        """Fallback flow that replies to the incoming message and returns message ID."""
        msg_any: Any = message

        async def do_reply() -> Any:
            kwargs = self._build_message_kwargs(
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            return await msg_any.reply_text(text, **kwargs)

        sent_message, success = await retry_telegram_operation(
            do_reply, operation_name="reply_text_with_id"
        )
        if not success or sent_message is None:
            logger.warning("reply_text_retry_failed", extra={"text_length": len(text)})
            return None

        logger.debug("reply_text_sent", extra={"length": len(text)})

        message_id = getattr(sent_message, "message_id", None)
        logger.debug(
            "reply_with_id_result",
            extra={"message_id": message_id, "sent_message_type": type(sent_message).__name__},
        )
        return message_id

    async def safe_reply_with_id(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> int | None:
        """Safely reply to a message and return the message ID for progress tracking with security checks."""
        prepared_text = self._prepare_text_for_reply_with_id(text, parse_mode)
        if prepared_text is None:
            return None
        text = prepared_text

        if not await self._validator.check_rate_limit():
            logger.warning("safe_reply_with_id_rate_limited", extra={"text_length": len(text)})

        if self._safe_reply_func is not None:
            try:
                client = getattr(getattr(self, "_telegram_client", None), "client", None)
                chat = getattr(message, "chat", None)
                chat_id = getattr(chat, "id", None) if chat is not None else None
                if client is not None and chat_id is not None and hasattr(client, "send_message"):
                    logger.debug(
                        "reply_with_client_for_id",
                        extra={
                            "text_length": len(text),
                            "has_parse_mode": parse_mode is not None,
                            "chat_id": chat_id,
                        },
                    )
                    message_id = await self._send_via_client_with_id(
                        client,
                        chat_id,
                        text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                        disable_web_page_preview=disable_web_page_preview,
                    )
                    if message_id is not None:
                        return message_id
            except Exception as e:
                raise_if_cancelled(e)
                logger.warning("reply_with_client_failed_fallback_custom", extra={"error": str(e)})

            logger.debug(
                "reply_with_custom_function",
                extra={"text_length": len(text), "has_parse_mode": parse_mode is not None},
            )
            try:
                await self._invoke_safe_reply_callback(
                    message,
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
            except Exception as e:
                raise_if_cancelled(e)
                logger.error(
                    "reply_failed",
                    exc_info=True,
                    extra={"error": str(e), "text_length": len(text)},
                )
                return None
            logger.warning("reply_with_id_no_message_id", extra={"reason": "custom_reply_function"})
            return None

        try:
            return await self._reply_text_with_id(
                message,
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception as e:
            raise_if_cancelled(e)
            logger.error(
                "reply_failed",
                exc_info=True,
                extra={"error": str(e), "text_length": len(text)},
            )
            return None

    async def edit_or_send(
        self,
        message: Any,
        text: str,
        message_id: int | None = None,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> int | None:
        """Edit existing message or send new if edit fails.

        This method provides a convenient pattern for progress updates:
        - If message_id is provided, tries to edit that message
        - If edit fails or no message_id, sends a new message
        - Returns the message_id for future edits

        Args:
            message: The original Telegram message (for chat_id and reply context)
            text: The text content to send/edit
            message_id: Optional message ID to edit
            parse_mode: Optional parse mode for text formatting

        Returns:
            Message ID for future edits, or None if both operations failed
        """
        chat_id = getattr(getattr(message, "chat", None), "id", None)

        # Try to edit if we have a message_id
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
            # Edit failed (maybe message was deleted), log and fall through to send
            logger.debug(
                "edit_or_send_edit_failed_fallback_send",
                extra={"chat_id": chat_id, "message_id": message_id},
            )

        # Send new message
        return await self.safe_reply_with_id(
            message,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
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
        """Edit an existing message in Telegram with security checks.

        Args:
            chat_id: The chat ID where the message exists
            message_id: The message ID to edit
            text: The new text content

        Returns:
            True if the message was successfully edited, False otherwise
        """
        text = self._prepare_text_for_edit(chat_id, message_id, text)
        if text is None:
            return False

        if not await self._validator.check_rate_limit():
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
        except Exception as e:
            raise_if_cancelled(e)
            logger.warning(
                "edit_message_failed",
                exc_info=True,
                extra={"error": str(e), "chat_id": chat_id, "message_id": message_id},
            )
            return False

    def _prepare_text_for_edit(self, chat_id: int, message_id: int, text: str) -> str | None:
        """Validate and normalize edit text before calling Telegram APIs."""
        if not text or not text.strip():
            logger.warning(
                "edit_message_empty_text",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return None

        is_safe, error_msg = self._validator.is_safe_content(text)
        if not is_safe:
            logger.warning(
                "edit_message_unsafe_content_blocked",
                extra={
                    "error": error_msg,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text_preview": text[:100],
                },
            )
            return None

        if len(text) > self._max_message_chars:
            logger.warning(
                "edit_message_too_long_truncating",
                extra={
                    "length": len(text),
                    "max": self._max_message_chars,
                    "chat_id": chat_id,
                    "message_id": message_id,
                },
            )
            text = text[: self._max_message_chars - 10] + "..."
        return text

    def _log_edit_attempt(self, chat_id: int, message_id: int) -> None:
        """Log edit attempt diagnostics once per request."""
        logger.debug(
            "edit_message_attempt",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "has_telegram_client": self._telegram_client is not None,
                "telegram_client_has_client": (
                    hasattr(self._telegram_client, "client") if self._telegram_client else False
                ),
                "client": self._telegram_client.client if self._telegram_client else None,
            },
        )

    def _resolve_edit_client(self, chat_id: int, message_id: int) -> Any | None:
        """Resolve Telegram client object for message editing."""
        if not self._telegram_client or not hasattr(self._telegram_client, "client"):
            logger.warning(
                "edit_message_no_telegram_client",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return None

        client = self._telegram_client.client
        if not client or not hasattr(client, "edit_message_text"):
            logger.warning(
                "edit_message_no_client_method",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return None
        return client

    def _validate_edit_identifiers(self, chat_id: int, message_id: int, text: str) -> bool:
        """Validate primitive edit call inputs before API invocation."""
        if isinstance(chat_id, int) and isinstance(message_id, int):
            return True
        logger.warning(
            "edit_message_invalid_params",
            extra={"chat_id": chat_id, "message_id": message_id, "text_length": len(text)},
        )
        return False

    def _build_edit_text(self, text: str, parse_mode: str | None) -> str:
        """Append UTC update hint for HTML progress edits."""
        if parse_mode != "HTML" or "Updated at" in text:
            return text
        now = datetime.now(UTC).strftime("%H:%M:%S")
        return f"{text}\n\n<i>Updated at {now} UTC</i>"

    @staticmethod
    def _is_message_not_modified_error(exc: Exception | None) -> bool:
        """Return True when Telegram edit failure is equivalent to success."""
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
        """Perform Telegram edit with retries and semantic success handling."""
        last_error_exc: Exception | None = None

        async def do_edit() -> None:
            nonlocal last_error_exc
            kwargs: dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": self._build_edit_text(text, parse_mode),
            }
            normalized_mode = _normalize_parse_mode(parse_mode)
            if normalized_mode is not None:
                kwargs["parse_mode"] = normalized_mode
            if reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            if disable_web_page_preview is not None:
                kwargs["disable_web_page_preview"] = disable_web_page_preview
            try:
                await client.edit_message_text(**kwargs)
            except Exception as e:
                raise_if_cancelled(e)
                last_error_exc = e
                raise

        _, success = await retry_telegram_operation(do_edit, operation_name="edit_message")
        if success:
            logger.debug(
                "edit_message_success", extra={"chat_id": chat_id, "message_id": message_id}
            )
            return True

        if self._is_message_not_modified_error(last_error_exc):
            logger.debug(
                "edit_message_not_modified_success",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return True

        logger.warning(
            "edit_message_retry_failed", extra={"chat_id": chat_id, "message_id": message_id}
        )
        return False

    async def send_chat_action(
        self,
        chat_id: int,
        action: str = "typing",
    ) -> bool:
        """Send a chat action (typing indicator) to Telegram.

        Args:
            chat_id: The chat ID to send the action to
            action: The action type. Valid values:
                - "typing" - typing text
                - "upload_photo" - uploading photo
                - "upload_video" - uploading video
                - "upload_document" - uploading document
                - "upload_audio" - uploading audio
                - "find_location" - finding location
                - "record_voice" - recording voice
                - "record_video" - recording video
                - "choose_sticker" - choosing sticker

        Returns:
            True if the action was sent successfully, False otherwise
        """
        try:
            if not isinstance(chat_id, int) or chat_id == 0:
                logger.debug("send_chat_action_invalid_chat_id", extra={"chat_id": chat_id})
                return False

            if self._telegram_client and hasattr(self._telegram_client, "client"):
                client = self._telegram_client.client
                if client and hasattr(client, "send_chat_action"):
                    try:
                        await client.send_chat_action(chat_id=chat_id, action=action)
                        logger.debug(
                            "chat_action_sent",
                            extra={"chat_id": chat_id, "action": action},
                        )
                        return True
                    except Exception as e:
                        raise_if_cancelled(e)
                        # Don't log as error - typing indicators are non-critical
                        logger.debug(
                            "chat_action_send_failed",
                            extra={"chat_id": chat_id, "action": action, "error": str(e)},
                        )
                        return False
                else:
                    logger.debug("chat_action_no_client_method", extra={"chat_id": chat_id})
                    return False
            else:
                logger.debug("chat_action_no_telegram_client", extra={"chat_id": chat_id})
                return False
        except Exception as e:
            raise_if_cancelled(e)
            logger.debug(
                "chat_action_exception",
                extra={"chat_id": chat_id, "action": action, "error": str(e)},
            )
            return False

    async def reply_json(
        self, message: Any, obj: dict, *, correlation_id: str | None = None, success: bool = True
    ) -> None:
        """Reply with JSON object, using file upload for large content."""
        if success and isinstance(obj, dict) and obj.get("success") in (True, False):
            payload = obj
        elif success:
            payload = success_response(obj, correlation_id=correlation_id)
        else:
            payload = obj

        if self._reply_json_func is not None:
            await self._reply_json_func(message, payload)
            return

        pretty = json.dumps(payload, ensure_ascii=False, indent=2)
        # Prefer sending as a document always to avoid size limits
        try:
            bio = io.BytesIO(pretty.encode("utf-8"))
            bio.name = self._build_json_filename(obj)
            msg_any: Any = message
            await msg_any.reply_document(bio, caption="📊 Full Summary JSON attached")
            return
        except Exception as e:
            raise_if_cancelled(e)
            logger.error("reply_document_failed", extra={"error": str(e)})
        await self.safe_reply(message, f"```json\n{pretty}\n```")

    def create_inline_keyboard(self, buttons: list[dict[str, str]]) -> Any:
        """Create an inline keyboard markup from button definitions.

        Args:
            buttons: List of button dictionaries with 'text' and 'callback_data' keys.
                    Each button dict should have 'text' (display text) and 'callback_data' (data sent when clicked).

        Returns:
            InlineKeyboardMarkup object or None if pyrogram is not available.

        Example:
            buttons = [
                {"text": "✅ Yes", "callback_data": "confirm_yes"},
                {"text": "❌ No", "callback_data": "confirm_no"}
            ]
            keyboard = create_inline_keyboard(buttons)
        """
        try:
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            # Create button rows - each button gets its own row for better mobile UX
            keyboard_buttons = [
                [InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"])]
                for btn in buttons
            ]
            return InlineKeyboardMarkup(keyboard_buttons)
        except ImportError:
            logger.warning("pyrogram_not_available_for_inline_keyboard")
            return None
        except Exception as e:
            logger.error("failed_to_create_inline_keyboard", extra={"error": str(e)})
            return None

    async def send_to_admin_log(self, text: str, *, correlation_id: str | None = None) -> None:
        """Send a debug message to the admin log chat.

        No-op when ``admin_log_chat_id`` is not configured. Swallows all
        exceptions so that admin logging never breaks the user-facing flow.
        """
        if self._admin_log_chat_id is None:
            return
        try:
            if correlation_id:
                text = f"[{correlation_id}] {text}"
            client = getattr(self._telegram_client, "client", None)
            if client is not None and hasattr(client, "send_message"):
                await client.send_message(chat_id=self._admin_log_chat_id, text=text[:4096])
        except Exception as e:
            raise_if_cancelled(e)
            logger.warning("admin_log_send_failed", extra={"chat_id": self._admin_log_chat_id})

    def _slugify(self, text: str, *, max_len: int = 60) -> str:
        """Create a filesystem-friendly slug from text."""
        text = text.strip().lower()
        # Replace non-word characters with hyphens
        text = re.sub(r"[^\w\-\s]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        if len(text) > max_len:
            text = text[:max_len].rstrip("-")
        return text or "summary"

    def _build_json_filename(self, obj: dict) -> str:
        """Build a descriptive filename for the JSON attachment."""
        # Prefer SEO keywords; fallback to first words of TL;DR
        seo = obj.get("seo_keywords") or []
        base: str | None = None
        if isinstance(seo, list) and seo:
            base = "-".join(self._slugify(str(x)) for x in seo[:3] if str(x).strip())
        if not base:
            tl = str(obj.get("summary_250", "")).strip()
            if tl:
                # Use first 6 words
                words = re.findall(r"\w+", tl)[:6]
                base = self._slugify("-".join(words))
        if not base:
            base = "summary"
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{base}-{timestamp}.json"
