# ruff: noqa: E501
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.telegram_models import TelegramMessage
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.response_formatter import ResponseFormatter
    from app.adapters.url_processor import URLProcessor
    from app.adapters.forward_processor import ForwardProcessor

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming message routing and basic command processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
        forward_processor: ForwardProcessor,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self.url_processor = url_processor
        self.forward_processor = forward_processor

        # Simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # Pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}

    async def handle_message(self, message: Any) -> None:
        """Main message handling entry point."""
        start_time = time.time()
        interaction_id = 0

        try:
            correlation_id = generate_correlation_id()

            # Parse message using comprehensive model for better validation
            telegram_message = TelegramMessage.from_pyrogram_message(message)

            # Validate message and log any issues
            validation_errors = telegram_message.validate()
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
                uid = 0
                logger.warning(
                    f"Invalid user ID type: {type(uid)}, setting to 0")

            logger.info(f"Checking access for UID: {uid} (type: {type(uid)})")
            logger.info(
                f"Allowed user IDs: {self.cfg.telegram.allowed_user_ids} (type: {type(self.cfg.telegram.allowed_user_ids)})"
            )
            chat_id = telegram_message.chat.id if telegram_message.chat else None
            message_id = telegram_message.message_id
            text = telegram_message.get_effective_text() or ""

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

            # Log the initial user interaction
            interaction_id = self._log_user_interaction(
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

            # Access control check
            if not await self._check_access(
                uid, message, correlation_id, interaction_id, start_time
            ):
                return

            # Route message based on content
            await self._route_message(
                message, text, uid, has_forward, correlation_id, interaction_id, start_time
            )

        except Exception as e:  # noqa: BLE001
            logger.exception("handler_error", extra={"cid": correlation_id})
            try:
                self._audit("ERROR", "unhandled_error", {
                            "cid": correlation_id, "error": str(e)})
            except Exception:
                pass
            await self.response_formatter.safe_reply(
                message,
                f"An unexpected error occurred. Error ID: {correlation_id}. Please try again.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(e)[:500],  # Limit error message length
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    async def _check_access(
        self, uid: int, message: Any, correlation_id: str, interaction_id: int, start_time: float
    ) -> bool:
        """Check if user has access to the bot."""
        # Owner-only gate - improved validation with better debugging
        if self.cfg.telegram.allowed_user_ids:
            logger.info(
                f"Access control enabled. Checking if UID {uid} is in allowed list: {self.cfg.telegram.allowed_user_ids}"
            )
            if uid not in self.cfg.telegram.allowed_user_ids:
                logger.warning(
                    f"Access denied for UID {uid}. Not in allowed list: {self.cfg.telegram.allowed_user_ids}"
                )
            else:
                logger.info(
                    f"Access granted for UID {uid}. Found in allowed list.")
        else:
            logger.info(
                "Access control disabled - no allowed_user_ids configured")

        if self.cfg.telegram.allowed_user_ids and uid not in self.cfg.telegram.allowed_user_ids:
            await self.response_formatter.safe_reply(
                message,
                f"This bot is private. Access denied. Error ID: {correlation_id}",
            )
            logger.info("access_denied", extra={
                        "uid": uid, "cid": correlation_id})
            try:
                self._audit("WARN", "access_denied", {
                            "uid": uid, "cid": correlation_id})
            except Exception:
                pass

            # Update interaction with access denied
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="Access denied",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return False
        return True

    async def _route_message(
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
        # Commands
        if text.startswith("/start"):
            await self._handle_start_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/help"):
            await self._handle_help_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/summarize_all"):
            await self._handle_summarize_all_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/summarize"):
            await self._handle_summarize_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # If awaiting a URL due to prior /summarize
        if uid in self._awaiting_url_users and looks_like_url(text):
            await self._handle_awaited_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Direct URL handling
        if text and looks_like_url(text):
            await self._handle_direct_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Handle yes/no responses for pending multi-link confirmation
        if uid in self._pending_multi_links:
            await self._handle_multi_link_confirmation(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        # Handle forwarded messages
        if getattr(message, "forward_from_chat", None) and getattr(
            message, "forward_from_message_id", None
        ):
            await self.forward_processor.handle_forward_flow(
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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _handle_start_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /start command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_start",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_start", {
                    "uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_welcome(message)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="welcome",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _handle_help_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /help command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_help",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_help", {
                    "uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_help(message)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="help",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _handle_summarize_all_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /summarize_all command."""
        urls = extract_all_urls(text)
        if len(urls) == 0:
            await self.response_formatter.safe_reply(
                message,
                "Send multiple URLs in one message after /summarize_all, separated by space or new line.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="No URLs found",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return

        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_summarize_all",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
                "count": len(urls),
            },
        )
        try:
            self._audit(
                "INFO",
                "command_summarize_all",
                {"uid": uid, "chat_id": chat_id,
                    "cid": correlation_id, "count": len(urls)},
            )
        except Exception:
            pass

        await self.response_formatter.safe_reply(message, f"Processing {len(urls)} links...")
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="processing",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        for u in urls:
            per_link_cid = generate_correlation_id()
            logger.debug("processing_link", extra={
                         "uid": uid, "url": u, "cid": per_link_cid})
            await self.url_processor.handle_url_flow(message, u, correlation_id=per_link_cid)

    async def _handle_summarize_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /summarize command."""
        urls = extract_all_urls(text)
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_summarize",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
                "with_urls": bool(urls),
                "count": len(urls),
            },
        )
        try:
            self._audit(
                "INFO",
                "command_summarize",
                {
                    "uid": uid,
                    "chat_id": chat_id,
                    "cid": correlation_id,
                    "with_urls": bool(urls),
                    "count": len(urls),
                },
            )
        except Exception:
            pass

        if len(urls) > 1:
            self._pending_multi_links[uid] = urls
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={
                         "uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
        elif len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )
        else:
            self._awaiting_url_users.add(uid)
            await self.response_formatter.safe_reply(message, "Send a URL to summarize.")
            logger.debug("awaiting_url", extra={"uid": uid})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="awaiting_url",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    async def _handle_awaited_url(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle URL sent after /summarize command."""
        urls = extract_all_urls(text)
        self._awaiting_url_users.discard(uid)

        if len(urls) > 1:
            self._pending_multi_links[uid] = urls
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={
                         "uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return

        if len(urls) == 1:
            logger.debug("received_awaited_url", extra={"uid": uid})
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )

    async def _handle_direct_url(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle direct URL message."""
        urls = extract_all_urls(text)

        if len(urls) > 1:
            self._pending_multi_links[uid] = urls
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={
                         "uid": uid, "count": len(urls)})
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
        elif len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )

    async def _handle_multi_link_confirmation(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle yes/no confirmation for multiple links."""
        if self._is_affirmative(text):
            urls = self._pending_multi_links.pop(uid)
            await self.response_formatter.safe_reply(message, f"Processing {len(urls)} links...")
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="processing",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            for u in urls:
                per_link_cid = generate_correlation_id()
                logger.debug(
                    "processing_link",
                    extra={"uid": uid, "url": u, "cid": per_link_cid},
                )
                await self.url_processor.handle_url_flow(message, u, correlation_id=per_link_cid)
            return

        if self._is_negative(text):
            self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(message, "Cancelled.")
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    def _is_affirmative(self, text: str) -> bool:
        """Check if text is an affirmative response."""
        t = text.strip().lower()
        return t in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        """Check if text is a negative response."""
        t = text.strip().lower()
        return t in {"n", "no", "-", "cancel", "stop", "нет", "не"}

    def _log_user_interaction(
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
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_log_placeholder",
            extra={
                "user_id": user_id,
                "interaction_type": interaction_type,
                "cid": correlation_id,
                "structured_output_enabled": self.cfg.openrouter.enable_structured_outputs,
            },
        )
        return 0

    def _update_user_interaction(
        self,
        *,
        interaction_id: int,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        """Update an existing user interaction record."""
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_update_placeholder",
            extra={"interaction_id": interaction_id,
                   "response_type": response_type},
        )

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper."""
        try:
            self.db.insert_audit_log(
                level=level, event=event, details_json=json.dumps(details, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.error("audit_persist_failed", extra={
                         "error": str(e), "event": event})
