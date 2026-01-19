"""Core Telegram message sending."""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.api.models.responses import success_response
from app.utils.retry_utils import retry_telegram_operation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.formatting.message_validator import MessageValidatorImpl

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the response sender.

        Args:
            validator: Message validator for security checks.
            max_message_chars: Maximum characters per message.
            safe_reply_func: Optional callback for test compatibility.
            reply_json_func: Optional callback for test compatibility.
            telegram_client: Optional Telegram client for message operations.
        """
        self._validator = validator
        self._max_message_chars = max_message_chars
        self._safe_reply_func = safe_reply_func
        self._reply_json_func = reply_json_func
        self._telegram_client = telegram_client

    async def safe_reply(
        self, message: Any, text: str, *, parse_mode: str | None = None, reply_markup: Any = None
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
            kwargs = {}
            if parse_mode is not None:
                kwargs["parse_mode"] = parse_mode
            if reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            await self._safe_reply_func(message, text, **kwargs)
            return

        try:
            msg_any: Any = message
            kwargs = {}
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            await msg_any.reply_text(text, **kwargs)
            try:
                logger.debug(
                    "reply_text_sent",
                    extra={"length": len(text), "has_buttons": reply_markup is not None},
                )
            except Exception:
                pass
        except Exception as e:
            logger.error("reply_failed", extra={"error": str(e), "text_length": len(text)})

    async def safe_reply_with_id(
        self, message: Any, text: str, *, parse_mode: str | None = None
    ) -> int | None:
        """Safely reply to a message and return the message ID for progress tracking with security checks."""
        # Input validation
        if not text or not text.strip():
            logger.warning(
                "safe_reply_with_id_empty_text", extra={"parse_mode": parse_mode is not None}
            )
            return None

        # Security content check
        is_safe, error_msg = self._validator.is_safe_content(text)
        if not is_safe:
            logger.warning(
                "safe_reply_with_id_unsafe_content_blocked",
                extra={"error": error_msg, "text_length": len(text), "text_preview": text[:100]},
            )
            # Send safe error message instead
            safe_text = "❌ Message blocked for security reasons."
            text = safe_text

        # Length check
        if len(text) > self._max_message_chars:
            logger.warning(
                "safe_reply_with_id_message_too_long",
                extra={"length": len(text), "max": self._max_message_chars},
            )
            # Truncate if too long
            text = text[: self._max_message_chars - 10] + "..."

        # Rate limiting check
        if not await self._validator.check_rate_limit():
            logger.warning("safe_reply_with_id_rate_limited", extra={"text_length": len(text)})

        if self._safe_reply_func is not None:
            # When a custom reply function is provided (e.g., compatibility layer),
            # we still want to obtain a Telegram message_id for progress updates.
            # If a Telegram client is available, prefer sending via the client so
            # that we can return the created message_id and enable edits.
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

                    # Define send operation for retry logic
                    async def do_send() -> Any:
                        if parse_mode is not None:
                            return await client.send_message(
                                chat_id=chat_id, text=text, parse_mode=parse_mode
                            )
                        return await client.send_message(chat_id=chat_id, text=text)

                    # Retry the send operation with exponential backoff
                    sent, success = await retry_telegram_operation(
                        do_send, operation_name="send_message_with_id"
                    )

                    if success and sent is not None:
                        message_id = getattr(sent, "message_id", None)
                        if message_id is None:
                            message_id = getattr(sent, "id", None)
                        logger.debug(
                            "reply_with_id_result",
                            extra={
                                "message_id": message_id,
                                "sent_message_type": type(sent).__name__,
                            },
                        )
                        return message_id
                    logger.warning(
                        "reply_with_id_retry_failed",
                        extra={"chat_id": chat_id, "text_length": len(text)},
                    )
                    return None
            except Exception as e:
                # Fall back to the custom function if direct client send failed
                logger.warning("reply_with_client_failed_fallback_custom", extra={"error": str(e)})

            logger.debug(
                "reply_with_custom_function",
                extra={"text_length": len(text), "has_parse_mode": parse_mode is not None},
            )
            kwargs = {"parse_mode": parse_mode} if parse_mode is not None else {}
            await self._safe_reply_func(message, text, **kwargs)
            logger.warning("reply_with_id_no_message_id", extra={"reason": "custom_reply_function"})
            return None  # Can't get message ID from custom function

        try:
            msg_any: Any = message

            # Define reply operation for retry logic
            async def do_reply() -> Any:
                if parse_mode:
                    return await msg_any.reply_text(text, parse_mode=parse_mode)
                return await msg_any.reply_text(text)

            # Retry the reply operation with exponential backoff
            sent_message, success = await retry_telegram_operation(
                do_reply, operation_name="reply_text_with_id"
            )

            if success and sent_message is not None:
                try:
                    logger.debug("reply_text_sent", extra={"length": len(text)})
                except Exception:
                    pass

                message_id = getattr(sent_message, "message_id", None)
                logger.debug(
                    "reply_with_id_result",
                    extra={
                        "message_id": message_id,
                        "sent_message_type": type(sent_message).__name__,
                    },
                )
                return message_id
            logger.warning(
                "reply_text_retry_failed",
                extra={"text_length": len(text)},
            )
            return None
        except Exception as e:
            logger.error("reply_failed", extra={"error": str(e), "text_length": len(text)})
            return None

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> bool:
        """Edit an existing message in Telegram with security checks.

        Args:
            chat_id: The chat ID where the message exists
            message_id: The message ID to edit
            text: The new text content

        Returns:
            True if the message was successfully edited, False otherwise
        """
        try:
            # Input validation
            if not text or not text.strip():
                logger.warning(
                    "edit_message_empty_text", extra={"chat_id": chat_id, "message_id": message_id}
                )
                return False

            # Security content check
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
                return False

            # Length check
            if len(text) > self._max_message_chars:
                logger.warning(
                    "edit_message_too_long",
                    extra={
                        "length": len(text),
                        "max": self._max_message_chars,
                        "chat_id": chat_id,
                        "message_id": message_id,
                    },
                )
                return False

            # Rate limiting check
            if not await self._validator.check_rate_limit():
                logger.warning(
                    "edit_message_rate_limited",
                    extra={"chat_id": chat_id, "message_id": message_id},
                )
                # Continue despite rate limit warning, but note it
                # This maintains backward compatibility

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

            if self._telegram_client and hasattr(self._telegram_client, "client"):
                client = self._telegram_client.client
                if client and hasattr(client, "edit_message_text"):
                    # Validate inputs before making the API call
                    if not isinstance(chat_id, int) or not isinstance(message_id, int):
                        logger.warning(
                            "edit_message_invalid_params",
                            extra={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "text_length": len(text),
                            },
                        )
                        return False

                    # Define API call for retry logic
                    async def do_edit() -> None:
                        await client.edit_message_text(
                            chat_id=chat_id, message_id=message_id, text=text
                        )

                    # Retry the API call with exponential backoff
                    _, success = await retry_telegram_operation(
                        do_edit, operation_name="edit_message"
                    )

                    if success:
                        logger.debug(
                            "edit_message_success",
                            extra={"chat_id": chat_id, "message_id": message_id},
                        )
                        return True
                    logger.warning(
                        "edit_message_retry_failed",
                        extra={"chat_id": chat_id, "message_id": message_id},
                    )
                    return False
                logger.warning(
                    "edit_message_no_client_method",
                    extra={"chat_id": chat_id, "message_id": message_id},
                )
                return False
            logger.warning(
                "edit_message_no_telegram_client",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return False
        except Exception as e:
            logger.warning(
                "edit_message_failed",
                extra={"error": str(e), "chat_id": chat_id, "message_id": message_id},
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
