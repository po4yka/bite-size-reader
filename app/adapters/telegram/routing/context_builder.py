"""Context preparation for Telegram message routing."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.adapter_models.telegram.telegram_message import TelegramMessage
from app.core.url_utils import extract_all_urls, looks_like_url

from .models import PreparedRouteContext

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import (
        ResponseFormatterFacade as ResponseFormatter,
    )

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageRouteContextBuilder:
    """Prepare normalized route context from a raw Telegram message."""

    _MAX_TEXT_LENGTH = 50 * 1024

    def __init__(
        self,
        response_formatter: ResponseFormatter,
        recent_message_ids: dict[tuple[int, int, int], tuple[float, str]],
        recent_message_ttl: int,
    ) -> None:
        self.response_formatter = response_formatter
        self._recent_message_ids = recent_message_ids
        self._recent_message_ttl = recent_message_ttl

    async def prepare(self, message: Any, correlation_id: str) -> PreparedRouteContext | None:
        """Build a normalized context or return None when processing should stop."""
        if self._should_skip_message(message, correlation_id):
            return None

        telegram_message = TelegramMessage.from_pyrogram_message(message)
        self._log_validation_errors(telegram_message, correlation_id)

        uid = await self._resolve_user_id(telegram_message, message, correlation_id)
        if uid is None:
            return None

        chat_id = telegram_message.chat.id if telegram_message.chat else None
        message_id = telegram_message.message_id
        text = telegram_message.get_effective_text() or ""

        if await self._text_limit_exceeded(message, text, uid, chat_id, correlation_id):
            return None

        message_key = (uid, chat_id or 0, message_id) if message_id is not None else None
        text_signature = text.strip() if isinstance(text, str) else ""
        if message_key:
            if self._check_duplicate(message_key, text_signature):
                logger.info(
                    "duplicate_message_skipped",
                    extra={"uid": uid, "chat_id": chat_id, "message_id": message_id},
                )
                return None
            self._record_message(message_key, text_signature)

        has_forward, forward_from_chat_id, forward_from_chat_title, forward_from_message_id = (
            self._extract_forward_details(telegram_message)
        )
        interaction_type, command, first_url = self._classify_interaction(
            telegram_message,
            text,
            has_forward,
        )
        media_type = telegram_message.media_type.value if telegram_message.media_type else None

        return PreparedRouteContext(
            message=message,
            telegram_message=telegram_message,
            text=text,
            uid=uid,
            chat_id=chat_id,
            message_id=message_id,
            has_forward=has_forward,
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            interaction_type=interaction_type,
            command=command,
            first_url=first_url,
            media_type=media_type,
            correlation_id=correlation_id,
        )

    def _should_skip_message(self, message: Any, correlation_id: str) -> bool:
        if bool(getattr(message, "outgoing", False)):
            logger.debug(
                "skip_outgoing_message",
                extra={"cid": correlation_id, "message_id": getattr(message, "id", None)},
            )
            return True

        from_user = getattr(message, "from_user", None)
        if from_user is None:
            logger.debug(
                "skip_message_without_from_user",
                extra={"cid": correlation_id, "message_id": getattr(message, "id", None)},
            )
            return True

        if bool(getattr(from_user, "is_bot", False)):
            logger.debug(
                "skip_bot_origin_message",
                extra={
                    "cid": correlation_id,
                    "message_id": getattr(message, "id", None),
                    "from_user_id": getattr(from_user, "id", None),
                },
            )
            return True
        return False

    def _log_validation_errors(
        self, telegram_message: TelegramMessage, correlation_id: str
    ) -> None:
        validation_errors = telegram_message.validate_message()
        if validation_errors:
            logger.warning(
                "message_validation_errors",
                extra={
                    "cid": correlation_id,
                    "errors": validation_errors,
                    "message_id": telegram_message.message_id,
                },
            )

    async def _resolve_user_id(
        self,
        telegram_message: TelegramMessage,
        message: Any,
        correlation_id: str,
    ) -> int | None:
        uid_value = telegram_message.from_user.id if telegram_message.from_user else 0
        try:
            return int(uid_value)
        except (ValueError, TypeError):
            logger.warning(
                "invalid_user_id_type",
                extra={"cid": correlation_id, "user_id_type": type(uid_value).__name__},
            )
            await self.response_formatter.safe_reply(
                message,
                "Unable to determine user identity. Message processing skipped.",
            )
            return None

    async def _text_limit_exceeded(
        self,
        message: Any,
        text: str,
        uid: int,
        chat_id: int | None,
        correlation_id: str,
    ) -> bool:
        if len(text) <= self._MAX_TEXT_LENGTH:
            return False

        logger.warning(
            "text_length_exceeded",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "text_length": len(text),
                "max_allowed": self._MAX_TEXT_LENGTH,
            },
        )
        await self.response_formatter.send_error_notification(
            message,
            "message_too_long",
            correlation_id,
            details=(
                f"The message is {len(text):,} characters long, "
                f"which exceeds the limit of {self._MAX_TEXT_LENGTH:,}."
            ),
        )
        return True

    def _extract_forward_details(
        self,
        telegram_message: TelegramMessage,
    ) -> tuple[bool, int | None, str | None, int | None]:
        has_forward = telegram_message.is_forwarded
        if not has_forward:
            return False, None, None, None

        forward_chat = telegram_message.forward_from_chat
        return (
            True,
            forward_chat.id if forward_chat else None,
            forward_chat.title if forward_chat else None,
            telegram_message.forward_from_message_id,
        )

    def _classify_interaction(
        self,
        telegram_message: TelegramMessage,
        text: str,
        has_forward: bool,
    ) -> tuple[str, str | None, str | None]:
        if telegram_message.is_command():
            return "command", telegram_message.get_command(), None
        if has_forward:
            return "forward", None, None
        if text and looks_like_url(text):
            urls = extract_all_urls(text)
            return "url", None, urls[0] if urls else None
        if text:
            return "text", None, None
        return "unknown", None, None

    def _check_duplicate(
        self,
        message_key: tuple[int, int, int],
        text_signature: str,
    ) -> bool:
        now = time.time()
        last_seen = self._recent_message_ids.get(message_key)
        return (
            last_seen is not None
            and now - last_seen[0] < self._recent_message_ttl
            and last_seen[1] == text_signature
        )

    def _record_message(
        self,
        message_key: tuple[int, int, int],
        text_signature: str,
    ) -> None:
        now = time.time()
        self._recent_message_ids[message_key] = (now, text_signature)
        if len(self._recent_message_ids) > 2000:
            cutoff = now - self._recent_message_ttl
            expired_keys = [
                key for key, (ts, _signature) in self._recent_message_ids.items() if ts < cutoff
            ]
            for key in expired_keys:
                del self._recent_message_ids[key]
