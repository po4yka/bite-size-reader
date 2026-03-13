"""Primary route entrypoint for Telegram message routing."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import ConcurrencyTimeoutError
from app.core.logging_utils import generate_correlation_id
from app.core.ui_strings import t
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.user_interactions import async_safe_update_user_interaction
from app.models.telegram.telegram_message import TelegramMessage

if TYPE_CHECKING:
    from app.security.rate_limiter import RedisUserRateLimiter, UserRateLimiter

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageRouterEntrypointMixin:
    """Top-level message handling flow for MessageRouter."""

    _MAX_TEXT_LENGTH = 50 * 1024
    _recent_message_ids: dict[tuple[int, int, int], tuple[float, str]]
    _recent_message_ttl: int

    async def route_message(self, message: Any) -> None:
        """Main message routing entry point."""
        start_time = time.time()
        interaction_id = 0
        uid = 0
        limiter: RedisUserRateLimiter | UserRateLimiter = self._rate_limiter
        concurrent_acquired = False
        correlation_id = generate_correlation_id()

        try:
            if self._should_skip_message(message, correlation_id):
                return

            telegram_message = TelegramMessage.from_pyrogram_message(message)
            self._log_validation_errors(telegram_message, correlation_id)

            uid = await self._resolve_user_id(telegram_message, message, correlation_id)
            if uid is None:
                return

            if not await self._check_user_access(uid, message, correlation_id, start_time):
                return

            route_ctx = await self._prepare_route_context(
                telegram_message=telegram_message,
                message=message,
                uid=uid,
                correlation_id=correlation_id,
            )
            if route_ctx is None:
                return

            limiter = await self._get_active_rate_limiter()

            interaction_id = await self._log_user_interaction(
                user_id=uid,
                chat_id=route_ctx["chat_id"],
                message_id=route_ctx["message_id"],
                interaction_type=route_ctx["interaction_type"],
                command=route_ctx["command"],
                input_text=route_ctx["text"][:1000] if route_ctx["text"] else None,
                input_url=route_ctx["input_url"],
                has_forward=route_ctx["has_forward"],
                forward_from_chat_id=route_ctx["forward_from_chat_id"],
                forward_from_chat_title=route_ctx["forward_from_chat_title"],
                forward_from_message_id=route_ctx["forward_from_message_id"],
                media_type=route_ctx["media_type"],
                correlation_id=correlation_id,
            )

            allowed, error_msg = await self._check_rate_limit(
                limiter, uid, route_ctx["interaction_type"]
            )
            if not allowed:
                await self._handle_rate_limit_rejection(
                    message=message,
                    uid=uid,
                    interaction_type=route_ctx["interaction_type"],
                    correlation_id=correlation_id,
                    error_msg=error_msg,
                    interaction_id=interaction_id,
                    start_time=start_time,
                )
                return

            if not await self._acquire_concurrent_slot(limiter, uid):
                await self._handle_concurrent_limit_rejection(
                    message=message,
                    uid=uid,
                    interaction_type=route_ctx["interaction_type"],
                    correlation_id=correlation_id,
                    interaction_id=interaction_id,
                    start_time=start_time,
                )
                return
            concurrent_acquired = True

            await self._route_message_content_with_tracking(
                message=message,
                text=route_ctx["text"],
                uid=uid,
                has_forward=route_ctx["has_forward"],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                start_time=start_time,
            )

        except asyncio.CancelledError:
            await self._handle_cancelled_route(
                correlation_id=correlation_id,
                uid=uid,
                interaction_id=interaction_id,
                start_time=start_time,
            )
            return
        except Exception as e:
            await self._handle_route_exception(
                message=message,
                error=e,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                start_time=start_time,
            )
        finally:
            if concurrent_acquired:
                await self._release_concurrent_slot(limiter, uid)

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
        self, telegram_message: TelegramMessage, message: Any, correlation_id: str
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
                message, "Unable to determine user identity. Message processing skipped."
            )
            return None

    async def _check_user_access(
        self,
        uid: int,
        message: Any,
        correlation_id: str,
        start_time: float,
    ) -> bool:
        logger.info(
            "checking_access_for_user",
            extra={"cid": correlation_id, "user_id": uid, "user_id_type": type(uid).__name__},
        )
        return await self.access_controller.check_access(
            uid, message, correlation_id, 0, start_time
        )

    async def _prepare_route_context(
        self,
        telegram_message: TelegramMessage,
        message: Any,
        uid: int,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        chat_id = telegram_message.chat.id if telegram_message.chat else None
        message_id = telegram_message.message_id
        text = telegram_message.get_effective_text() or ""

        if await self._text_limit_exceeded(message, text, uid, chat_id, correlation_id):
            return None

        message_key = (uid, chat_id or 0, message_id) if message_id is not None else None
        text_signature = text.strip() if isinstance(text, str) else ""
        if message_key and self._is_duplicate_message(message_key, text_signature):
            logger.info(
                "duplicate_message_skipped",
                extra={"uid": uid, "chat_id": chat_id, "message_id": message_id},
            )
            return None

        has_forward, forward_from_chat_id, forward_from_chat_title, forward_from_message_id = (
            self._extract_forward_details(telegram_message)
        )
        interaction_type, command, input_url = self._classify_interaction(
            telegram_message, text, has_forward
        )
        media_type = telegram_message.media_type.value if telegram_message.media_type else None

        return {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "has_forward": has_forward,
            "forward_from_chat_id": forward_from_chat_id,
            "forward_from_chat_title": forward_from_chat_title,
            "forward_from_message_id": forward_from_message_id,
            "interaction_type": interaction_type,
            "command": command,
            "input_url": input_url,
            "media_type": media_type,
        }

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
        self, telegram_message: TelegramMessage
    ) -> tuple[bool, int | None, str | None, int | None]:
        has_forward = telegram_message.is_forwarded
        if not has_forward:
            return False, None, None, None

        forward_chat = telegram_message.forward_from_chat
        forward_from_chat_id = forward_chat.id if forward_chat else None
        forward_from_chat_title = forward_chat.title if forward_chat else None
        return (
            True,
            forward_from_chat_id,
            forward_from_chat_title,
            telegram_message.forward_from_message_id,
        )

    def _classify_interaction(
        self, telegram_message: TelegramMessage, text: str, has_forward: bool
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

    async def _handle_rate_limit_rejection(
        self,
        message: Any,
        uid: int,
        interaction_type: str,
        correlation_id: str,
        error_msg: str | None,
        interaction_id: int,
        start_time: float,
    ) -> None:
        logger.warning(
            "rate_limit_rejected",
            extra={"uid": uid, "interaction_type": interaction_type, "cid": correlation_id},
        )
        if error_msg and self._should_notify_rate_limit(uid):
            await self.response_formatter.safe_reply(message, error_msg)
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="rate_limited",
                error_occurred=True,
                error_message="Rate limit exceeded",
                start_time=start_time,
                logger_=logger,
            )

    async def _handle_concurrent_limit_rejection(
        self,
        message: Any,
        uid: int,
        interaction_type: str,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        logger.warning(
            "concurrent_limit_rejected",
            extra={"uid": uid, "interaction_type": interaction_type, "cid": correlation_id},
        )
        await self.response_formatter.safe_reply(message, t("concurrent_ops_limit", self._lang))
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="concurrent_limited",
                error_occurred=True,
                error_message="Concurrent operations limit exceeded",
                start_time=start_time,
                logger_=logger,
            )

    def _is_duplicate_message(
        self,
        message_key: tuple[int, int, int],
        text_signature: str,
    ) -> bool:
        now = time.time()
        last_seen = self._recent_message_ids.get(message_key)
        if (
            last_seen is not None
            and now - last_seen[0] < self._recent_message_ttl
            and last_seen[1] == text_signature
        ):
            return True
        self._recent_message_ids[message_key] = (now, text_signature)
        if len(self._recent_message_ids) > 2000:
            cutoff = now - self._recent_message_ttl
            self._recent_message_ids = {
                key: (ts, signature)
                for key, (ts, signature) in self._recent_message_ids.items()
                if ts >= cutoff
            }
        return False

    async def _route_message_content_with_tracking(
        self,
        message: Any,
        text: str,
        uid: int,
        has_forward: bool,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        if self._task_manager is not None:
            async with self._task_manager.track(uid, enabled=not text.startswith("/cancel")):
                await self._route_message_content(
                    message,
                    text,
                    uid,
                    has_forward,
                    correlation_id,
                    interaction_id,
                    start_time,
                )
            return

        await self._route_message_content(
            message,
            text,
            uid,
            has_forward,
            correlation_id,
            interaction_id,
            start_time,
        )

    async def _handle_cancelled_route(
        self,
        correlation_id: str,
        uid: int,
        interaction_id: int,
        start_time: float,
    ) -> None:
        logger.info(
            "message_processing_cancelled",
            extra={"cid": correlation_id, "uid": uid},
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=False,
                response_type="cancelled",
                start_time=start_time,
                logger_=logger,
            )

    async def _handle_route_exception(
        self,
        message: Any,
        error: Exception,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        logger.exception("handler_error", extra={"cid": correlation_id})
        self._audit_route_exception(correlation_id, error)
        await self._notify_route_exception(message, correlation_id, error)
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="error",
                error_occurred=True,
                error_message=str(error)[:500],
                start_time=start_time,
                logger_=logger,
            )

    def _audit_route_exception(self, correlation_id: str, error: Exception) -> None:
        try:
            self._audit("ERROR", "unhandled_error", {"cid": correlation_id, "error": str(error)})
        except Exception as audit_error:
            logger.error(
                "audit_logging_failed",
                extra={
                    "cid": correlation_id,
                    "original_error": str(error),
                    "audit_error": str(audit_error),
                    "audit_error_type": type(audit_error).__name__,
                },
            )

    async def _notify_route_exception(
        self, message: Any, correlation_id: str, error: Exception
    ) -> None:
        error_text = str(error)
        error_lower = error_text.lower()

        if isinstance(error, ConcurrencyTimeoutError):
            await self.response_formatter.send_error_notification(
                message,
                "rate_limit",
                correlation_id,
                details="The system is currently handling too many requests. Please try again in a few moments.",
            )
            return

        if "timeout" in error_lower or isinstance(error, TimeoutError):
            await self.response_formatter.send_error_notification(
                message,
                "timeout",
                correlation_id,
                details="The request timed out. The article might be too large or the service is temporarily slow.",
            )
            return

        if "rate limit" in error_lower or "429" in error_text:
            await self.response_formatter.send_error_notification(
                message,
                "rate_limit",
                correlation_id,
                details="The service is currently busy. Please retry in a few minutes.",
            )
            return

        if any(keyword in error_lower for keyword in ("connection", "network", "unreachable")):
            await self.response_formatter.send_error_notification(
                message,
                "network_error",
                correlation_id,
                details="A network error occurred. Please check your connection or try again later.",
            )
            return

        if any(keyword in error_lower for keyword in ("database", "sqlite", "disk")):
            await self.response_formatter.send_error_notification(
                message,
                "database_error",
                correlation_id,
                details="An internal database error occurred. This is usually temporary.",
            )
            return

        await self.response_formatter.send_error_notification(
            message, "unexpected_error", correlation_id
        )
