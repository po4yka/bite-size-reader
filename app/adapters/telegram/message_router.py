"""Message routing and coordination for Telegram bot."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import ConcurrencyTimeoutError
from app.adapters.telegram.message_router_helpers import (
    handle_document_file,
    is_duplicate_message,
    is_txt_file_with_urls,
    should_notify_rate_limit,
)
from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.session import DatabaseSessionManager
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.infrastructure.redis import get_redis
from app.models.telegram.telegram_message import TelegramMessage
from app.security.file_validation import SecureFileValidator
from app.security.rate_limiter import RateLimitConfig, RedisUserRateLimiter, UserRateLimiter

if TYPE_CHECKING:
    from app.adapters.attachment.attachment_processor import AttachmentProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.access_controller import AccessController
    from app.adapters.telegram.command_processor import CommandProcessor
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.url_handler import URLHandler

logger = logging.getLogger(__name__)


# ...
class MessageRouter:
    """Main message routing and coordination logic."""

    # ruff: noqa: E501

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        access_controller: AccessController,
        command_processor: CommandProcessor,
        url_handler: URLHandler,
        forward_processor: ForwardProcessor,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        task_manager: UserTaskManager | None = None,
        attachment_processor: AttachmentProcessor | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.access_controller = access_controller
        self.command_processor = command_processor
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.attachment_processor = attachment_processor
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._task_manager = task_manager

        # Store reference to URL processor for silent processing
        self._url_processor = url_handler.url_processor

        # Initialize security components
        self._rate_limiter_config = RateLimitConfig(
            max_requests=cfg.api_limits.requests_limit,
            window_seconds=cfg.api_limits.window_seconds,
            max_concurrent=cfg.api_limits.max_concurrent,
            cooldown_multiplier=cfg.api_limits.cooldown_multiplier,
        )
        self._rate_limiter = UserRateLimiter(self._rate_limiter_config)
        self._redis_limiter: RedisUserRateLimiter | None = None
        self._redis_limiter_available: bool | None = None
        self._file_validator = SecureFileValidator(
            max_file_size=10 * 1024 * 1024  # 10 MB max file size
        )
        self._rate_limit_notified_until: dict[int, float] = {}
        self._rate_limit_notice_window = max(self._rate_limiter_config.window_seconds, 30)
        self._recent_message_ids: dict[tuple[int, int, int], tuple[float, str]] = {}
        self._recent_message_ttl = 120

    async def _get_active_rate_limiter(self) -> RedisUserRateLimiter | UserRateLimiter:
        if self._redis_limiter_available is None:
            redis_client = await get_redis(self.cfg)
            if redis_client:
                self._redis_limiter = RedisUserRateLimiter(
                    redis_client, self._rate_limiter_config, self.cfg.redis.prefix
                )
                self._redis_limiter_available = True
                logger.info("telegram_rate_limiter_redis_enabled")
            else:
                self._redis_limiter_available = False
        return (
            self._redis_limiter
            if self._redis_limiter_available and self._redis_limiter
            else self._rate_limiter
        )

    async def _check_rate_limit(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int, interaction_type: str
    ) -> tuple[bool, str | None]:
        return await limiter.check_and_record(uid, operation=interaction_type)

    async def _acquire_concurrent_slot(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int
    ) -> bool:
        return await limiter.acquire_concurrent_slot(uid)

    async def _release_concurrent_slot(
        self, limiter: RedisUserRateLimiter | UserRateLimiter, uid: int
    ) -> None:
        await limiter.release_concurrent_slot(uid)

    async def cleanup_rate_limiter(self) -> int:
        """Clean up expired rate limiter entries to prevent memory leaks.

        Only cleans up the in-memory rate limiter; Redis handles TTL automatically.
        Also cleans up expired notification-suppression and recent message entries.
        Returns the number of users cleaned up.
        """
        cleaned = await self._rate_limiter.cleanup_expired()

        # Clean up expired rate-limit notification suppression entries
        now = time.time()
        expired_notifs = [
            uid for uid, deadline in self._rate_limit_notified_until.items() if now >= deadline
        ]
        for uid in expired_notifs:
            del self._rate_limit_notified_until[uid]

        # Clean up expired recent message IDs
        cutoff = now - self._recent_message_ttl
        expired_msgs = [key for key, (ts, _sig) in self._recent_message_ids.items() if ts < cutoff]
        for key in expired_msgs:
            del self._recent_message_ids[key]

        return cleaned

    async def route_message(self, message: Any) -> None:
        """Main message routing entry point."""
        start_time = time.time()
        interaction_id = 0
        uid = 0
        limiter: RedisUserRateLimiter | UserRateLimiter = self._rate_limiter
        concurrent_acquired = False

        try:
            correlation_id = generate_correlation_id()

            # Parse message using comprehensive model for better validation
            telegram_message = TelegramMessage.from_pyrogram_message(message)

            # Validate message and log any issues
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

            # Extract message details for logging using validated model
            uid = telegram_message.from_user.id if telegram_message.from_user else 0
            # Ensure uid is an integer for consistent comparison
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

            # CRITICAL: Validate text length to prevent memory exhaustion and regex DoS
            # Limit to 50KB for text processing (prevents regex DoS and memory issues)
            MAX_TEXT_LENGTH = 50 * 1024  # 50KB
            if len(text) > MAX_TEXT_LENGTH:
                logger.warning(
                    "text_length_exceeded",
                    extra={
                        "uid": uid,
                        "chat_id": chat_id,
                        "text_length": len(text),
                        "max_allowed": MAX_TEXT_LENGTH,
                    },
                )
                await self.response_formatter.send_error_notification(
                    message,
                    "message_too_long",
                    correlation_id,
                    details=f"The message is {len(text):,} characters long, which exceeds the limit of {MAX_TEXT_LENGTH:,}.",
                )
                return

            text_signature = text.strip() if isinstance(text, str) else ""
            if message_key and is_duplicate_message(self, message_key, text_signature):
                logger.info(
                    "duplicate_message_skipped",
                    extra={
                        "uid": uid,
                        "chat_id": chat_id,
                        "message_id": message_id,
                    },
                )
                return

            # Check for forwarded message using validated model
            has_forward = telegram_message.is_forwarded
            forward_from_chat_id = None
            forward_from_chat_title = None
            forward_from_message_id = None

            if has_forward:
                if telegram_message.forward_from_chat:
                    forward_from_chat_id = telegram_message.forward_from_chat.id
                    forward_from_chat_title = telegram_message.forward_from_chat.title
                forward_from_message_id = telegram_message.forward_from_message_id

            # Get media type using validated model
            media_type = telegram_message.media_type.value if telegram_message.media_type else None

            # Determine interaction type using validated model
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

            # Select rate limiter (Redis preferred, fallback in-memory)
            limiter = await self._get_active_rate_limiter()

            # Log the initial user interaction after access is confirmed
            interaction_id = await self._log_user_interaction(
                user_id=uid,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=text[:1000] if text else None,  # Limit text length
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                correlation_id=correlation_id,
            )

            # Rate limiting check
            allowed, error_msg = await self._check_rate_limit(limiter, uid, interaction_type)
            if not allowed:
                logger.warning(
                    "rate_limit_rejected",
                    extra={
                        "uid": uid,
                        "interaction_type": interaction_type,
                        "cid": correlation_id,
                    },
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

            # Acquire concurrent slot
            if not await self._acquire_concurrent_slot(limiter, uid):
                logger.warning(
                    "concurrent_limit_rejected",
                    extra={"uid": uid, "interaction_type": interaction_type, "cid": correlation_id},
                )
                await self.response_formatter.safe_reply(
                    message,
                    "⏸️ Too many concurrent operations. Please wait for your previous requests to complete.",
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
                # Always release concurrent slot
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
            # Release concurrent slot on cancellation
            if concurrent_acquired:
                await self._release_concurrent_slot(limiter, uid)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("handler_error", extra={"cid": correlation_id})
            try:
                self._audit("ERROR", "unhandled_error", {"cid": correlation_id, "error": str(e)})
            except Exception as audit_error:
                # Log audit failure but don't fail the error handling
                logger.error(
                    "audit_logging_failed",
                    extra={
                        "cid": correlation_id,
                        "original_error": str(e),
                        "audit_error": str(audit_error),
                        "audit_error_type": type(audit_error).__name__,
                    },
                )
            # Classify the error for a more helpful user-facing message
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
                    error_message=str(e)[:500],  # Limit error message length
                    start_time=start_time,
                    logger_=logger,
                )
            # Release concurrent slot on error
            if concurrent_acquired:
                await self._release_concurrent_slot(limiter, uid)

    async def handle_multi_confirm_response(self, message: Any, uid: int, response: str) -> None:
        """Handle multi-link confirmation response from button or text.

        Args:
            message: The Telegram message object
            uid: User ID
            response: The response text ("yes" or "no")
        """
        # Generate correlation ID and start time for this interaction
        correlation_id = generate_correlation_id()
        start_time = time.time()

        # Log interaction
        interaction_id = await self._log_user_interaction(
            user_id=uid,
            chat_id=getattr(getattr(message, "chat", None), "id", None),
            message_id=getattr(message, "message_id", 0) or getattr(message, "id", 0),
            interaction_type="confirmation",
            command=None,
            input_text=response,
            input_url=None,
            has_forward=False,
            forward_from_chat_id=None,
            forward_from_chat_title=None,
            forward_from_message_id=None,
            media_type=None,
            correlation_id=correlation_id,
        )

        # Call the existing URL handler method
        await self.url_handler.handle_multi_link_confirmation(
            message, response, uid, correlation_id, interaction_id, start_time
        )

    async def _route_message_content(
        self,
        message: Any,
        text: str,
        uid: int,
        has_forward: bool,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Route message to appropriate handler based on content."""
        if text.startswith("/start"):
            await self.command_processor.handle_start_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/help"):
            await self.command_processor.handle_help_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/dbinfo"):
            await self.command_processor.handle_dbinfo_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/dbverify"):
            await self.command_processor.handle_dbverify_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        for local_command in ("/finddb", "/findlocal"):
            if text.startswith(local_command):
                await self.command_processor.handle_find_local_command(
                    message,
                    text,
                    uid,
                    correlation_id,
                    interaction_id,
                    start_time,
                    command=local_command,
                )
                return

        for online_command in ("/findweb", "/findonline", "/find"):
            if text.startswith(online_command):
                await self.command_processor.handle_find_online_command(
                    message,
                    text,
                    uid,
                    correlation_id,
                    interaction_id,
                    start_time,
                    command=online_command,
                )
                return

        if text.startswith("/summarize_all"):
            await self.command_processor.handle_summarize_all_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/summarize"):
            action, should_continue = await self.command_processor.handle_summarize_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            if action == "multi_confirm":
                await self.url_handler.add_pending_multi_links(uid, extract_all_urls(text))
            elif action == "awaiting_url":
                await self.url_handler.add_awaiting_user(uid)
            return

        if text.startswith("/cancel"):
            await self.command_processor.handle_cancel_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/unread"):
            await self.command_processor.handle_unread_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/read"):
            await self.command_processor.handle_read_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/search"):
            await self.command_processor.handle_search_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/sync_karakeep"):
            await self.command_processor.handle_sync_karakeep_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/debug"):
            await self.command_processor.handle_debug_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        # Handle forwarded messages before URL routing so forwards containing links aren't misclassified
        if has_forward:
            fwd_chat = getattr(message, "forward_from_chat", None)
            fwd_msg_id = getattr(message, "forward_from_message_id", None)
            fwd_from_user = getattr(message, "forward_from", None)
            fwd_sender_name = getattr(message, "forward_sender_name", None)

            # Channel forwards (primary use case): have both chat and message ID
            if fwd_chat is not None and fwd_msg_id is not None:
                await self.forward_processor.handle_forward_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return

            # User forwards and privacy-protected forwards: process if there's text content
            if fwd_from_user is not None or fwd_sender_name:
                fwd_text = (
                    getattr(message, "text", None) or getattr(message, "caption", None) or ""
                ).strip()
                if fwd_text:
                    await self.forward_processor.handle_forward_flow(
                        message, correlation_id=correlation_id, interaction_id=interaction_id
                    )
                    return
                # Media-only forward from user — check for image/PDF attachment
                if self.attachment_processor and self._should_handle_attachment(message):
                    await self.attachment_processor.handle_attachment_flow(
                        message, correlation_id=correlation_id, interaction_id=interaction_id
                    )
                    return
                logger.info(
                    "forward_skipped_no_text",
                    extra={
                        "cid": correlation_id,
                        "has_fwd_user": fwd_from_user is not None,
                        "has_fwd_sender_name": bool(fwd_sender_name),
                    },
                )
                await self.response_formatter.safe_reply(
                    message,
                    "This forwarded message has no text content to summarize. "
                    "Please forward a message that contains text.",
                )
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.user_repo,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="forward_no_text",
                        start_time=start_time,
                        logger_=logger,
                    )
                return

            # Fallback: forward with only forward_date (privacy-restricted channels)
            # Process if there's text content to summarize
            fwd_text = (
                getattr(message, "text", None) or getattr(message, "caption", None) or ""
            ).strip()
            if fwd_text:
                await self.forward_processor.handle_forward_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return
            # Forward with no identifiable source and no text — check for attachment
            if self.attachment_processor and self._should_handle_attachment(message):
                await self.attachment_processor.handle_attachment_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return
            logger.info(
                "forward_skipped_unrecognized",
                extra={
                    "cid": correlation_id,
                    "has_forward_date": getattr(message, "forward_date", None) is not None,
                },
            )
            await self.response_formatter.safe_reply(
                message,
                "This forwarded message has no text content to summarize. "
                "Please forward a message that contains text.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="forward_no_text",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        # If awaiting a URL due to prior /summarize
        if await self.url_handler.is_awaiting_url(uid) and looks_like_url(text):
            await self.url_handler.handle_awaited_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Direct URL handling
        if text and looks_like_url(text):
            await self.url_handler.handle_direct_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Handle yes/no responses for pending multi-link confirmation
        if await self.url_handler.has_pending_multi_links(uid):
            await self.url_handler.handle_multi_link_confirmation(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Handle document files (.txt files containing URLs)
        if is_txt_file_with_urls(message):
            await handle_document_file(self, message, correlation_id, interaction_id, start_time)
            return

        # Handle media attachments (images, PDFs)
        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return

        # Default response for unknown input
        await self.response_formatter.safe_reply(message, "Send a URL or forward a channel post.")
        logger.debug(
            "unknown_input",
            extra={
                "has_forward": bool(getattr(message, "forward_from_chat", None)),
                "text_len": len(text),
            },
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                start_time=start_time,
                logger_=logger,
            )

    async def _log_user_interaction(
        self,
        *,
        user_id: int,
        chat_id: int | None = None,
        message_id: int | None = None,
        interaction_type: str,
        command: str | None = None,
        input_text: str | None = None,
        input_url: str | None = None,
        has_forward: bool = False,
        forward_from_chat_id: int | None = None,
        forward_from_chat_title: str | None = None,
        forward_from_message_id: int | None = None,
        media_type: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Log a user interaction and return the interaction ID."""

        try:
            interaction_id = await self.user_repo.async_insert_user_interaction(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=input_text,
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                correlation_id=correlation_id,
                structured_output_enabled=self.cfg.openrouter.enable_structured_outputs,
            )
            return interaction_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "user_interaction_log_failed",
                extra={
                    "error": str(exc),
                    "user_id": user_id,
                    "interaction_type": interaction_type,
                    "cid": correlation_id,
                },
            )
            return 0

    @staticmethod
    def _should_handle_attachment(message: Any) -> bool:
        """Check if the message contains a supported attachment (image or PDF)."""
        if getattr(message, "photo", None):
            return True
        doc = getattr(message, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or ""
            if mime.startswith("image/") or mime == "application/pdf":
                return True
        return False
