"""Primary route entrypoint for Telegram message routing."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import ConcurrencyTimeoutError
from app.adapters.telegram.message_router_helpers import (
    is_duplicate_message,
    should_notify_rate_limit,
)
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

    async def route_message(self, message: Any) -> None:
        """Main message routing entry point."""
        start_time = time.time()
        interaction_id = 0
        uid = 0
        limiter: RedisUserRateLimiter | UserRateLimiter = self._rate_limiter
        concurrent_acquired = False

        try:
            correlation_id = generate_correlation_id()

            if bool(getattr(message, "outgoing", False)):
                logger.debug(
                    "skip_outgoing_message",
                    extra={"cid": correlation_id, "message_id": getattr(message, "id", None)},
                )
                return

            from_user = getattr(message, "from_user", None)
            if from_user is None:
                logger.debug(
                    "skip_message_without_from_user",
                    extra={"cid": correlation_id, "message_id": getattr(message, "id", None)},
                )
                return

            if bool(getattr(from_user, "is_bot", False)):
                logger.debug(
                    "skip_bot_origin_message",
                    extra={
                        "cid": correlation_id,
                        "message_id": getattr(message, "id", None),
                        "from_user_id": getattr(from_user, "id", None),
                    },
                )
                return

            telegram_message = TelegramMessage.from_pyrogram_message(message)

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

            uid = telegram_message.from_user.id if telegram_message.from_user else 0
            try:
                uid = int(uid)
            except (ValueError, TypeError):
                logger.warning(
                    "invalid_user_id_type",
                    extra={"cid": correlation_id, "user_id_type": type(uid).__name__},
                )
                await self.response_formatter.safe_reply(
                    message, "Unable to determine user identity. Message processing skipped."
                )
                return

            logger.info(
                "checking_access_for_user",
                extra={"cid": correlation_id, "user_id": uid, "user_id_type": type(uid).__name__},
            )
            if not await self.access_controller.check_access(
                uid, message, correlation_id, 0, start_time
            ):
                return

            chat_id = telegram_message.chat.id if telegram_message.chat else None
            message_id = telegram_message.message_id
            message_key = None
            if message_id is not None:
                message_key = (uid, chat_id or 0, message_id)

            text = telegram_message.get_effective_text() or ""

            max_text_length = 50 * 1024
            if len(text) > max_text_length:
                logger.warning(
                    "text_length_exceeded",
                    extra={
                        "uid": uid,
                        "chat_id": chat_id,
                        "text_length": len(text),
                        "max_allowed": max_text_length,
                    },
                )
                await self.response_formatter.send_error_notification(
                    message,
                    "message_too_long",
                    correlation_id,
                    details=(
                        f"The message is {len(text):,} characters long, "
                        f"which exceeds the limit of {max_text_length:,}."
                    ),
                )
                return

            text_signature = text.strip() if isinstance(text, str) else ""
            if message_key and is_duplicate_message(self, message_key, text_signature):
                logger.info(
                    "duplicate_message_skipped",
                    extra={"uid": uid, "chat_id": chat_id, "message_id": message_id},
                )
                return

            has_forward = telegram_message.is_forwarded
            forward_from_chat_id = None
            forward_from_chat_title = None
            forward_from_message_id = None

            if has_forward:
                if telegram_message.forward_from_chat:
                    forward_from_chat_id = telegram_message.forward_from_chat.id
                    forward_from_chat_title = telegram_message.forward_from_chat.title
                forward_from_message_id = telegram_message.forward_from_message_id

            media_type = telegram_message.media_type.value if telegram_message.media_type else None

            interaction_type = "unknown"
            command = None
            input_url = None

            if telegram_message.is_command():
                interaction_type = "command"
                command = telegram_message.get_command()
            elif has_forward:
                interaction_type = "forward"
            elif text and looks_like_url(text):
                interaction_type = "url"
                urls = extract_all_urls(text)
                input_url = urls[0] if urls else None
            elif text:
                interaction_type = "text"

            limiter = await self._get_active_rate_limiter()

            interaction_id = await self._log_user_interaction(
                user_id=uid,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=text[:1000] if text else None,
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                correlation_id=correlation_id,
            )

            allowed, error_msg = await self._check_rate_limit(limiter, uid, interaction_type)
            if not allowed:
                logger.warning(
                    "rate_limit_rejected",
                    extra={"uid": uid, "interaction_type": interaction_type, "cid": correlation_id},
                )
                if error_msg and should_notify_rate_limit(self, uid):
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
                return

            if not await self._acquire_concurrent_slot(limiter, uid):
                logger.warning(
                    "concurrent_limit_rejected",
                    extra={"uid": uid, "interaction_type": interaction_type, "cid": correlation_id},
                )
                await self.response_formatter.safe_reply(
                    message, t("concurrent_ops_limit", self._lang)
                )
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
                return
            concurrent_acquired = True

            try:
                if self._task_manager is not None:
                    async with self._task_manager.track(
                        uid, enabled=not text.startswith("/cancel")
                    ):
                        await self._route_message_content(
                            message,
                            text,
                            uid,
                            has_forward,
                            correlation_id,
                            interaction_id,
                            start_time,
                        )
                else:
                    await self._route_message_content(
                        message,
                        text,
                        uid,
                        has_forward,
                        correlation_id,
                        interaction_id,
                        start_time,
                    )
            finally:
                if concurrent_acquired:
                    await self._release_concurrent_slot(limiter, uid)

        except asyncio.CancelledError:
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
            if concurrent_acquired:
                await self._release_concurrent_slot(limiter, uid)
            return
        except Exception as e:
            logger.exception("handler_error", extra={"cid": correlation_id})
            try:
                self._audit("ERROR", "unhandled_error", {"cid": correlation_id, "error": str(e)})
            except Exception as audit_error:
                logger.error(
                    "audit_logging_failed",
                    extra={
                        "cid": correlation_id,
                        "original_error": str(e),
                        "audit_error": str(audit_error),
                        "audit_error_type": type(audit_error).__name__,
                    },
                )
            error_lower = str(e).lower()

            if isinstance(e, ConcurrencyTimeoutError):
                await self.response_formatter.send_error_notification(
                    message,
                    "rate_limit",
                    correlation_id,
                    details="The system is currently handling too many requests. Please try again in a few moments.",
                )
            elif "timeout" in error_lower or isinstance(e, TimeoutError):
                await self.response_formatter.send_error_notification(
                    message,
                    "timeout",
                    correlation_id,
                    details="The request timed out. The article might be too large or the service is temporarily slow.",
                )
            elif "rate limit" in error_lower or "429" in str(e):
                await self.response_formatter.send_error_notification(
                    message,
                    "rate_limit",
                    correlation_id,
                    details="The service is currently busy. Please retry in a few minutes.",
                )
            elif any(kw in error_lower for kw in ("connection", "network", "unreachable")):
                await self.response_formatter.send_error_notification(
                    message,
                    "network_error",
                    correlation_id,
                    details="A network error occurred. Please check your connection or try again later.",
                )
            elif "database" in error_lower or "sqlite" in error_lower or "disk" in error_lower:
                await self.response_formatter.send_error_notification(
                    message,
                    "database_error",
                    correlation_id,
                    details="An internal database error occurred. This is usually temporary.",
                )
            else:
                await self.response_formatter.send_error_notification(
                    message, "unexpected_error", correlation_id
                )

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(e)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
            if concurrent_acquired:
                await self._release_concurrent_slot(limiter, uid)
