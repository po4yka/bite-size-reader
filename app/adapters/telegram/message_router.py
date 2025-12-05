"""Message routing and coordination for Telegram bot."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx

from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction
from app.models.telegram.telegram_models import TelegramMessage
from app.security.file_validation import FileValidationError, SecureFileValidator
from app.security.rate_limiter import RateLimitConfig, UserRateLimiter
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.message_formatter import (
    create_progress_bar,
    format_completion_message,
    format_progress_message,
)
from app.utils.progress_tracker import ProgressTracker

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.access_controller import AccessController
    from app.adapters.telegram.command_processor import CommandProcessor
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.url_handler import URLHandler
    from app.models.batch_processing import URLProcessingResult

logger = logging.getLogger(__name__)


class MessageRouter:
    """Main message routing and coordination logic."""

    # ruff: noqa: E501

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        access_controller: AccessController,
        command_processor: CommandProcessor,
        url_handler: URLHandler,
        forward_processor: ForwardProcessor,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        task_manager: UserTaskManager | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.access_controller = access_controller
        self.command_processor = command_processor
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._task_manager = task_manager

        # Store reference to URL processor for silent processing
        self._url_processor = url_handler.url_processor

        # Initialize security components
        self._rate_limiter_config = RateLimitConfig(
            max_requests=10,  # 10 requests per window
            window_seconds=60,  # 60 second window
            max_concurrent=3,  # Max 3 concurrent operations per user
            cooldown_multiplier=2.0,  # 2x window cooldown after limit
        )
        self._rate_limiter = UserRateLimiter(self._rate_limiter_config)
        self._file_validator = SecureFileValidator(
            max_file_size=10 * 1024 * 1024  # 10 MB max file size
        )
        self._rate_limit_notified_until: dict[int, float] = {}
        self._rate_limit_notice_window = max(self._rate_limiter_config.window_seconds, 30)
        self._recent_message_ids: dict[tuple[int, int, int], tuple[float, str]] = {}
        self._recent_message_ttl = 120

    async def route_message(self, message: Any) -> None:
        """Main message routing entry point."""
        start_time = time.time()
        interaction_id = 0
        uid = 0

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
                logger.warning(f"Invalid user ID type: {type(uid)}, skipping message processing")
                await self.response_formatter.safe_reply(
                    message, "Unable to determine user identity. Message processing skipped."
                )
                return

            logger.info(f"Checking access for UID: {uid} (type: {type(uid)})")
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
                await self.response_formatter.safe_reply(
                    message,
                    f"❌ Message too long ({len(text):,} characters). "
                    f"Maximum allowed: {MAX_TEXT_LENGTH:,} characters. "
                    "Please split into smaller messages or use a file upload.",
                )
                return

            text_signature = text.strip() if isinstance(text, str) else ""
            if message_key and self._is_duplicate_message(message_key, text_signature):
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

            # Log the initial user interaction after access is confirmed
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
            # Rate limiting check
            allowed, error_msg = await self._rate_limiter.check_and_record(
                uid, operation=interaction_type
            )
            if not allowed:
                logger.warning(
                    "rate_limit_rejected",
                    extra={
                        "uid": uid,
                        "interaction_type": interaction_type,
                        "cid": correlation_id,
                    },
                )
                if error_msg and self._should_notify_rate_limit(uid):
                    await self.response_formatter.safe_reply(message, error_msg)
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.db,
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
            if not await self._rate_limiter.acquire_concurrent_slot(uid):
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
                        self.db,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="concurrent_limited",
                        error_occurred=True,
                        error_message="Concurrent operations limit exceeded",
                        start_time=start_time,
                        logger_=logger,
                    )
                return

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
                await self._rate_limiter.release_concurrent_slot(uid)

        except asyncio.CancelledError:
            logger.info(
                "message_processing_cancelled",
                extra={"cid": correlation_id, "uid": uid},
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=False,
                    response_type="cancelled",
                    start_time=start_time,
                    logger_=logger,
                )
            # Release concurrent slot on cancellation
            await self._rate_limiter.release_concurrent_slot(uid)
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
            await self.response_formatter.safe_reply(
                message,
                f"An unexpected error occurred. Error ID: {correlation_id}. Please try again.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(e)[:500],  # Limit error message length
                    start_time=start_time,
                    logger_=logger,
                )
            # Release concurrent slot on error
            await self._rate_limiter.release_concurrent_slot(uid)

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
        interaction_id = self._log_user_interaction(
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

        # Handle forwarded messages before URL routing so forwards containing links aren't misclassified
        if (
            has_forward
            and getattr(message, "forward_from_chat", None)
            and getattr(message, "forward_from_message_id", None)
        ):
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
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
        if self._is_txt_file_with_urls(message):
            await self._handle_document_file(message, correlation_id, interaction_id, start_time)
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
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                start_time=start_time,
                logger_=logger,
            )

    def _is_txt_file_with_urls(self, message: Any) -> bool:
        """Check if message contains a .txt document that likely contains URLs."""
        if not hasattr(message, "document"):
            return False

        document = getattr(message, "document", None)
        if not document or not hasattr(document, "file_name"):
            return False

        file_name = document.file_name
        # Check if it's a .txt file
        return file_name.lower().endswith(".txt")

    async def _handle_document_file(
        self,
        message: Any,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle .txt file processing (files containing URLs)."""
        file_path = None
        try:
            # Download and parse the file
            file_path = await self._download_file(message)
            if not file_path:
                await self.response_formatter.safe_reply(message, "Failed to download the file.")
                return

            # Parse URLs from the file with security validation
            try:
                urls = self._parse_txt_file(file_path)
            except FileValidationError as e:
                logger.error(
                    "file_validation_failed",
                    extra={"error": str(e), "cid": correlation_id},
                )
                await self.response_formatter.safe_reply(
                    message, f"❌ File validation failed: {str(e)}"
                )
                return

            if not urls:
                await self.response_formatter.safe_reply(
                    message, "No valid URLs found in the file."
                )
                return

            # Security check: limit batch size
            if len(urls) > self.response_formatter.MAX_BATCH_URLS:
                await self.response_formatter.safe_reply(
                    message,
                    f"❌ Too many URLs ({len(urls)}). Maximum allowed: {self.response_formatter.MAX_BATCH_URLS}.",
                )
                logger.warning(
                    "batch_url_limit_exceeded",
                    extra={
                        "url_count": len(urls),
                        "max_allowed": self.response_formatter.MAX_BATCH_URLS,
                    },
                )
                return

            # Validate each URL for security
            valid_urls = []
            for url in urls:
                is_valid, error_msg = self.response_formatter._validate_url(url)
                if is_valid:
                    valid_urls.append(url)
                else:
                    logger.warning("invalid_url_in_batch", extra={"url": url, "error": error_msg})

            if not valid_urls:
                await self.response_formatter.safe_reply(
                    message, "❌ No valid URLs found in the file after security checks."
                )
                return

            # Use only valid URLs
            urls = valid_urls

            # Send initial confirmation message (kept as a standalone message)
            await self.response_formatter.safe_reply(
                message, f"📄 File accepted. Processing {len(urls)} links."
            )
            # Respect formatter rate limits before sending the progress message we'll edit later
            try:
                initial_gap = max(
                    0.12,
                    (self.response_formatter.MIN_MESSAGE_INTERVAL_MS + 10) / 1000.0,
                )
                await asyncio.sleep(initial_gap)
            except Exception:
                pass
            # Create a dedicated progress message that we will edit in-place
            progress_message_id = await self.response_formatter.safe_reply_with_id(
                message,
                f"🔄 Processing links: 0/{len(urls)}\n{create_progress_bar(0, len(urls))}",
            )
            logger.debug(
                "document_file_processing_started",
                extra={"url_count": len(urls)},
            )

            # Process URLs with optimized parallel processing and memory management
            await self._process_urls_sequentially(
                message,
                urls,
                correlation_id,
                interaction_id,
                start_time,
                progress_message_id,
            )

            # Ensure we do not hit rate limiter after the last progress edit
            try:
                # Sleep a bit longer than the formatter's rate limit to ensure delivery
                min_gap_sec = max(
                    0.6,
                    (self.response_formatter.MIN_MESSAGE_INTERVAL_MS + 50) / 1000.0,
                )
                await asyncio.sleep(min_gap_sec)
            except Exception:
                pass

            # Completion message will be sent after processing is complete

        except Exception:
            logger.exception("document_file_processing_error", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message, "An error occurred while processing the file."
            )
        finally:
            # Clean up downloaded file with retry logic
            if file_path:
                cleanup_attempts = 0
                max_cleanup_attempts = 3
                cleanup_success = False

                while cleanup_attempts < max_cleanup_attempts and not cleanup_success:
                    try:
                        self._file_validator.cleanup_file(file_path)
                        cleanup_success = True
                    except PermissionError as e:
                        cleanup_attempts += 1
                        if cleanup_attempts >= max_cleanup_attempts:
                            logger.error(
                                "file_cleanup_permission_denied",
                                extra={
                                    "error": str(e),
                                    "file_path": file_path,
                                    "cid": correlation_id,
                                    "attempts": cleanup_attempts,
                                },
                            )
                        else:
                            # Wait and retry for permission errors
                            await asyncio.sleep(0.1 * cleanup_attempts)
                    except FileNotFoundError:
                        # File already deleted, this is fine
                        cleanup_success = True
                    except Exception as e:
                        cleanup_attempts += 1
                        logger.error(
                            "file_cleanup_unexpected_error",
                            extra={
                                "error": str(e),
                                "file_path": file_path,
                                "cid": correlation_id,
                                "error_type": type(e).__name__,
                                "attempts": cleanup_attempts,
                            },
                        )
                        break  # Don't retry unexpected errors

    async def _download_file(self, message: Any) -> str | None:
        """Download document file to temporary location."""
        try:
            # Get file path from Telegram
            document = getattr(message, "document", None)
            if not document:
                return None

            # Download file using bot's get_file method
            file_info = await message.download()
            return str(file_info) if file_info else None

        except Exception as e:
            logger.error("file_download_failed", extra={"error": str(e)})
            return None

    def _parse_txt_file(self, file_path: str) -> list[str]:
        """Parse URLs from .txt file with security validation.

        Args:
            file_path: Path to text file containing URLs

        Returns:
            List of validated URLs found in file

        Raises:
            FileValidationError: If file validation fails

        Security:
            All URLs are validated using normalize_url() which:
            - Checks for dangerous schemes (javascript:, file:, data:, etc.)
            - Validates URL structure and hostname
            - Blocks localhost, 127.0.0.1, and other suspicious domains
            - Prevents SSRF attacks
        """
        from app.core.url_utils import normalize_url

        # Use secure file validator to read file
        lines = self._file_validator.safe_read_text_file(file_path)

        # Extract and validate URLs from lines
        urls = []
        skipped_count = 0
        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Basic format check - starts with http/https
            if line.startswith("http://") or line.startswith("https://"):
                # Check for suspicious patterns (whitespace in URL)
                if " " in line or "\t" in line:
                    logger.warning(
                        "suspicious_url_skipped",
                        extra={
                            "url_preview": line[:50],
                            "reason": "contains whitespace",
                            "line_num": line_num,
                        },
                    )
                    skipped_count += 1
                    continue

                # CRITICAL: Validate URL for security (prevents SSRF)
                try:
                    # normalize_url() performs comprehensive security validation:
                    # - Blocks dangerous schemes (javascript:, file:, data:, etc.)
                    # - Validates URL structure
                    # - Checks for malicious patterns
                    normalized = normalize_url(line)
                    urls.append(normalized)
                except ValueError as e:
                    # URL failed security validation
                    logger.warning(
                        "invalid_url_in_file",
                        extra={
                            "url_preview": line[:50],
                            "error": str(e),
                            "line_num": line_num,
                            "file_path": file_path,
                        },
                    )
                    skipped_count += 1
            elif line.startswith(("http", "www")):
                # Possibly a URL without proper protocol
                logger.warning(
                    "malformed_url_skipped",
                    extra={
                        "url_preview": line[:50],
                        "reason": "invalid protocol",
                        "line_num": line_num,
                    },
                )
                skipped_count += 1

        logger.info(
            "file_parsed_successfully",
            extra={
                "file_path": file_path,
                "urls_found": len(urls),
                "urls_skipped": skipped_count,
                "lines_read": len(lines),
            },
        )

        return urls

    async def _process_urls_sequentially(
        self,
        message: Any,
        urls: list[str],
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        progress_message_id: int | None = None,
    ) -> None:
        """Process URLs with optimized parallel processing and batch progress updates."""
        total = len(urls)

        # Use semaphore to limit concurrent processing (prevent overwhelming external APIs)
        # CRITICAL: Limit concurrent tasks to prevent memory exhaustion
        # Each task can use 10-50MB (content + LLM API calls)
        # 5 concurrent × 50MB = 250MB max (safe for 2GB servers)
        # Previous value of 20 could cause 1GB+ spikes and OOM kills
        semaphore = asyncio.Semaphore(min(5, total))  # Max 5 concurrent URLs

        # Circuit breaker: stop processing if too many failures indicate service issues
        # Threshold: Allow up to 1/3 failures before opening circuit
        failure_threshold = min(10, max(3, total // 3))
        circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            timeout=60.0,  # Wait 60s before testing recovery
            success_threshold=3,  # Need 3 successes to close circuit
        )

        async def process_single_url(
            url: str, progress_tracker: ProgressTracker, max_retries: int = 3
        ) -> tuple[str, bool, str]:
            """Process a single URL with retry logic and return (url, success, error_message).

            Args:
                url: URL to process
                progress_tracker: Progress tracker for batch updates
                max_retries: Maximum number of retry attempts (default: 3)

            Returns:
                Tuple of (url, success, error_message)
            """
            from app.models.batch_processing import URLProcessingResult

            async with semaphore:
                # Check circuit breaker before processing
                if not circuit_breaker.can_proceed():
                    error_msg = "Circuit breaker open - service unavailable"
                    logger.warning(
                        "circuit_breaker_blocked_request",
                        extra={
                            "url": url,
                            "breaker_stats": circuit_breaker.get_stats(),
                        },
                    )
                    breaker_result: tuple[str, bool, str] = (url, False, error_msg)
                    # Don't increment progress here - will be done in finally block
                    try:
                        return breaker_result
                    finally:
                        await progress_tracker.increment_and_update()

                per_link_cid = generate_correlation_id()
                logger.info(
                    "processing_url_from_file",
                    extra={"url": url, "cid": per_link_cid},
                )

                final_result: tuple[str, bool, str] | None = None

                try:
                    # Retry logic with exponential backoff
                    for attempt in range(1, max_retries + 1):
                        try:
                            # Process URL with timeout
                            result = await asyncio.wait_for(
                                self._process_url_silently(
                                    message, url, per_link_cid, interaction_id
                                ),
                                timeout=600,  # 10 minute timeout per URL
                            )

                            # Check if successful
                            if result.success:
                                logger.debug(
                                    "process_single_url_success",
                                    extra={
                                        "url": url,
                                        "cid": per_link_cid,
                                        "attempt": attempt,
                                        "processing_time_ms": result.processing_time_ms,
                                    },
                                )
                                circuit_breaker.record_success()  # Record success for circuit breaker
                                final_result = (url, True, "")
                                return final_result

                            # Check if retry is possible
                            if not result.retry_possible or attempt >= max_retries:
                                logger.debug(
                                    "process_single_url_failure_final",
                                    extra={
                                        "url": url,
                                        "cid": per_link_cid,
                                        "attempt": attempt,
                                        "error_type": result.error_type,
                                        "retry_possible": result.retry_possible,
                                    },
                                )
                                circuit_breaker.record_failure()  # Record failure for circuit breaker
                                error_msg = result.error_message or "URL processing failed"
                                final_result = (url, False, error_msg)
                                return final_result

                            # Retry is possible - wait with exponential backoff
                            wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                            logger.info(
                                "retrying_url_processing",
                                extra={
                                    "url": url,
                                    "cid": per_link_cid,
                                    "attempt": attempt,
                                    "max_retries": max_retries,
                                    "wait_time": wait_time,
                                    "error_type": result.error_type,
                                },
                            )
                            await asyncio.sleep(wait_time)

                        except asyncio.TimeoutError:
                            error_msg = (
                                f"Timeout after 10 minutes (attempt {attempt}/{max_retries})"
                            )
                            logger.error(
                                "url_processing_timeout",
                                extra={"url": url, "cid": per_link_cid, "attempt": attempt},
                            )

                            # Retry timeouts if we have attempts left
                            if attempt < max_retries:
                                wait_time = 2 ** (attempt - 1)
                                logger.info(
                                    "retrying_after_timeout",
                                    extra={"url": url, "wait_time": wait_time},
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                circuit_breaker.record_failure()  # Record timeout as failure
                                final_result = (url, False, error_msg)
                                return final_result

                        except Exception as e:
                            error_msg = f"{type(e).__name__}: {str(e)}"
                            logger.error(
                                "url_processing_exception",
                                extra={
                                    "url": url,
                                    "cid": per_link_cid,
                                    "attempt": attempt,
                                    "error_type": type(e).__name__,
                                },
                            )

                            # Don't retry unexpected exceptions
                            circuit_breaker.record_failure()  # Record exception as failure
                            final_result = (url, False, error_msg)
                            return final_result

                    # Should not reach here, but handle it
                    error_msg = f"Processing failed after {max_retries} attempts"
                    circuit_breaker.record_failure()  # Record exhausted retries as failure
                    final_result = (url, False, error_msg)
                    return final_result

                except asyncio.CancelledError:
                    # Don't update progress on cancellation, just re-raise
                    raise

                finally:
                    # CRITICAL FIX: Single progress update in finally block
                    # This guarantees exactly-once semantics and prevents race conditions
                    if final_result is not None:  # Only update if processing completed
                        await progress_tracker.increment_and_update()

        # Process URLs in parallel with controlled concurrency and memory optimization
        # For very large batches (>30 URLs), process in chunks to manage memory
        chunk_size = 30 if total > 30 else total
        # Variables will be set from batch processing results

        # Thread-safe progress tracking with proper isolation using shared ProgressTracker
        async def progress_formatter(
            current: int, total_count: int, msg_id: int | None
        ) -> int | None:
            """Format and send progress updates."""
            return await self._send_progress_update(message, current, total_count, msg_id)

        progress_tracker = ProgressTracker(
            total=total,
            progress_formatter=progress_formatter,
            initial_message_id=progress_message_id,
            small_batch_threshold=10,
        )

        # Process URLs in true memory-efficient batches
        # File processing can use larger batches since users expect bulk processing
        batch_size = min(5, total)  # Process max 5 URLs at a time to limit memory and API load

        async def process_batches():
            """Process URL batches with progress tracking."""
            from app.models.batch_processing import FailedURLDetail

            batch_successful = 0
            batch_failed = 0
            batch_failed_urls: list[FailedURLDetail] = []

            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_urls = urls[batch_start:batch_end]

                # Create tasks for this batch only
                batch_tasks = [process_single_url(url, progress_tracker) for url in batch_urls]

                # Process batch and handle results immediately
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Process results from this batch immediately
                for result in batch_results:
                    # Progress is already incremented in process_single_url() - no double counting

                    # Debug logging to understand what results we're getting
                    logger.debug(
                        "batch_result_debug",
                        extra={
                            "result_type": type(result).__name__,
                            "result_value": (
                                str(result)[:200]
                                if not isinstance(result, Exception)
                                else str(result)
                            ),
                            "is_tuple": isinstance(result, tuple),
                            "tuple_len": len(result) if isinstance(result, tuple) else 0,
                            "cid": correlation_id,
                        },
                    )

                    if isinstance(result, Exception):
                        # Handle asyncio-specific exceptions properly
                        if isinstance(result, asyncio.CancelledError):
                            # Re-raise cancellation
                            raise result
                        # This should rarely happen due to return_exceptions=True, but handle it
                        batch_failed += 1
                        logger.error(
                            "unexpected_task_exception",
                            extra={"error": str(result), "cid": correlation_id},
                        )
                        batch_failed_urls.append(
                            FailedURLDetail(
                                url="Unknown URL",
                                error_type=type(result).__name__,
                                error_message=str(result),
                                retry_recommended=False,
                                attempts=1,
                            )
                        )
                    elif isinstance(result, tuple) and len(result) == 3:
                        url, success, error_msg = result
                        if success:
                            batch_successful += 1
                        else:
                            batch_failed += 1
                            # Classify error type from error message
                            error_type = "unknown"
                            retry_recommended = False
                            if "timeout" in error_msg.lower():
                                error_type = "timeout"
                                retry_recommended = True
                            elif "circuit breaker" in error_msg.lower():
                                error_type = "circuit_breaker"
                                retry_recommended = True
                            elif (
                                "network" in error_msg.lower() or "connection" in error_msg.lower()
                            ):
                                error_type = "network"
                                retry_recommended = True
                            elif (
                                "validation" in error_msg.lower() or "invalid" in error_msg.lower()
                            ):
                                error_type = "validation"
                                retry_recommended = False

                            batch_failed_urls.append(
                                FailedURLDetail(
                                    url=url,
                                    error_type=error_type,
                                    error_message=error_msg,
                                    retry_recommended=retry_recommended,
                                    attempts=3,  # Assume max retries
                                )
                            )
                            if error_msg:
                                logger.debug(
                                    "url_processing_failed_detail",
                                    extra={"url": url, "error": error_msg, "cid": correlation_id},
                                )
                    elif isinstance(result, tuple) and len(result) == 2:
                        # Backward compatibility with old format
                        url, success = result
                        if success:
                            batch_successful += 1
                        else:
                            batch_failed += 1
                            batch_failed_urls.append(
                                FailedURLDetail(
                                    url=url,
                                    error_type="unknown",
                                    error_message="No error details (legacy format)",
                                    retry_recommended=True,
                                    attempts=1,
                                )
                            )
                            logger.warning(
                                "legacy_result_format", extra={"url": url, "cid": correlation_id}
                            )
                    else:
                        # Unexpected result type - this is a programming error
                        batch_failed += 1
                        logger.error(
                            "unexpected_result_type",
                            extra={
                                "result_type": type(result).__name__,
                                "result_value": str(result)[:200],  # Truncate for logging
                                "cid": correlation_id,
                            },
                        )
                        batch_failed_urls.append(
                            FailedURLDetail(
                                url="Unknown URL",
                                error_type="unexpected_result",
                                error_message=f"Unexpected result type: {type(result).__name__}",
                                retry_recommended=False,
                                attempts=1,
                            )
                        )

            # Small delay between batches to prevent overwhelming external APIs
            if batch_end < total:
                await asyncio.sleep(0.1)

            return batch_successful, batch_failed, batch_failed_urls

        # Run batch processing and progress updates concurrently
        from app.models.batch_processing import FailedURLDetail

        progress_task = asyncio.create_task(progress_tracker.process_update_queue())
        batch_result: tuple[int, int, list[FailedURLDetail]] | Exception
        try:
            batch_result = await process_batches()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            batch_result = exc
        finally:
            progress_tracker.mark_complete()
            try:
                await progress_task
            except asyncio.CancelledError:
                raise
            except Exception as progress_exc:  # noqa: BLE001
                logger.warning(
                    "progress_update_worker_failed",
                    extra={"error": str(progress_exc)},
                )

        if isinstance(batch_result, Exception):
            from app.models.batch_processing import FailedURLDetail

            logger.error(
                "batch_processing_failed",
                extra={"error": str(batch_result), "cid": correlation_id},
            )
            # Set default values if batch processing failed
            successful = 0
            failed = total
            completed = total
            failed_urls: list[FailedURLDetail] = [
                FailedURLDetail(
                    url="batch",
                    error_type=type(batch_result).__name__,
                    error_message=f"Batch processing failed: {str(batch_result)}",
                    retry_recommended=False,
                    attempts=1,
                )
            ]
        elif isinstance(batch_result, tuple) and len(batch_result) == 3:
            # Unpack the results from process_batches()
            successful, failed, failed_urls = batch_result
            completed = successful + failed
        else:
            from app.models.batch_processing import FailedURLDetail

            # Unexpected result type
            logger.error(
                "unexpected_batch_result_type",
                extra={"result_type": type(batch_result).__name__, "cid": correlation_id},
            )
            successful = 0
            failed = total
            completed = total
            failed_urls = [
                FailedURLDetail(
                    url="batch",
                    error_type="unexpected_result",
                    error_message=f"Unexpected batch result type: {type(batch_result).__name__}",
                    retry_recommended=False,
                    attempts=1,
                )
            ]

        # Final progress update to ensure 100% completion is shown
        try:
            final_message_id = await self._send_progress_update(
                message, total, total, progress_tracker.message_id
            )
            if final_message_id is not None:
                progress_tracker.message_id = final_message_id
        except Exception as e:
            logger.warning("final_progress_update_failed", extra={"error": str(e)})

        # Send completion message with statistics
        logger.debug(
            "sending_completion_message",
            extra={"url_count": total, "successful": successful, "failed": len(failed_urls)},
        )

        # Create completion message with statistics using shared formatter
        completion_message = format_completion_message(
            total=total,
            successful=successful,
            failed=len(failed_urls),
            context="links",
            show_stats=True,
        )

        # Add error breakdown if there are failures with details
        if failed_urls and isinstance(failed_urls[0], FailedURLDetail):
            # Group errors by type
            error_breakdown: dict[str, list[FailedURLDetail]] = {}
            for failed_url in failed_urls:
                error_breakdown.setdefault(failed_url.error_type, []).append(failed_url)

            # Build error summary
            error_summary_parts = ["\n\n**Failure Breakdown:**"]
            for error_type, urls in error_breakdown.items():  # type: ignore[assignment]
                retry_note = " (retry recommended)" if urls[0].retry_recommended else ""  # type: ignore[attr-defined]
                error_summary_parts.append(f"\n• **{error_type}**: {len(urls)} URL(s){retry_note}")

            # Show first 3 failed URLs with details
            error_summary_parts.append("\n\n**Failed URLs (first 3):**")
            for i, failed_url in enumerate(failed_urls[:3], 1):
                url_display = (
                    failed_url.url if len(failed_url.url) <= 60 else f"{failed_url.url[:57]}..."
                )
                error_display = (
                    failed_url.error_message
                    if len(failed_url.error_message) <= 100
                    else f"{failed_url.error_message[:97]}..."
                )
                error_summary_parts.append(f"\n{i}. {url_display}\n   Error: {error_display}")

            completion_message += "".join(error_summary_parts)

        await self.response_formatter.safe_reply(message, completion_message)

        # Safety check: ensure all URLs were processed
        if completed != total:
            logger.error(
                "batch_processing_count_mismatch",
                extra={
                    "expected_total": total,
                    "actual_completed": completed,
                    "successful": successful,
                    "failed": len(failed_urls),
                },
            )
            # This should never happen, but if it does, log it as a critical error
            await self.response_formatter.safe_reply(
                message,
                f"⚠️ Processing completed with count mismatch. Expected {total}, processed {completed}.",
            )

        # Log results
        logger.info(
            "batch_processing_complete",
            extra={
                "total": total,
                "completed": completed,
                "successful": successful,
                "failed": len(failed_urls),
                "failed_urls": failed_urls[:5],  # Log first 5 failed URLs
                "processing_time_ms": int((time.time() - start_time) * 1000),
                "count_match": completed == total,
            },
        )

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="batch_processing_complete",
                start_time=start_time,
                logger_=logger,
            )

    async def _process_url_silently(
        self,
        message: Any,
        url: str,
        correlation_id: str,
        interaction_id: int,
    ) -> URLProcessingResult:
        """Process a single URL without sending Telegram responses.

        Returns:
            URLProcessingResult: Detailed result with error context
        """
        import time

        from app.core.async_utils import raise_if_cancelled
        from app.models.batch_processing import URLProcessingResult

        start_time = time.time()

        try:
            # Call the URL processor's handle_url_flow method with silent=True
            await self._url_processor.handle_url_flow(
                message,
                url,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                silent=True,
            )
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            return URLProcessingResult.success_result(url, processing_time_ms=processing_time)

        except asyncio.TimeoutError as e:
            raise_if_cancelled(e)
            logger.error(
                "url_processing_timeout",
                extra={"url": url, "cid": correlation_id, "error": str(e)},
            )
            return URLProcessingResult.timeout_result(url, timeout_sec=600)

        except (httpx.NetworkError, httpx.ConnectError, httpx.TimeoutException) as e:
            raise_if_cancelled(e)
            logger.error(
                "url_processing_network_error",
                extra={"url": url, "cid": correlation_id, "error": str(e)},
            )
            return URLProcessingResult.network_error_result(url, e)

        except ValueError as e:
            raise_if_cancelled(e)
            logger.error(
                "url_processing_validation_error",
                extra={"url": url, "cid": correlation_id, "error": str(e)},
            )
            return URLProcessingResult.validation_error_result(url, e)

        except Exception as e:
            raise_if_cancelled(e)
            logger.error(
                "url_processing_failed",
                extra={
                    "url": url,
                    "cid": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return URLProcessingResult.generic_error_result(url, e)

    async def _send_progress_update(
        self, message: Any, current: int, total: int, message_id: int | None = None
    ) -> int | None:
        """Send or edit the Telegram progress message.

        Returns the message ID that should be used for subsequent edits when available.
        """

        progress_text = format_progress_message(current, total, context="links", show_bar=True)

        chat_id = getattr(message.chat, "id", None)

        if message_id is not None and chat_id is not None:
            # Try to edit the existing message
            edit_success = await self.response_formatter.edit_message(
                chat_id, message_id, progress_text
            )

            if edit_success:
                logger.debug(
                    "progress_update_edited",
                    extra={
                        "current": current,
                        "total": total,
                        "message_id": message_id,
                        "text_length": len(progress_text),
                    },
                )
                return message_id
            else:
                logger.warning(
                    "progress_update_edit_failed",
                    extra={
                        "current": current,
                        "total": total,
                        "message_id": message_id,
                        "fallback": "will_send_new_message",
                    },
                )
                # Fall through to send new message below
        elif message_id is not None:
            logger.warning(
                "progress_update_no_chat_id",
                extra={"message_id": message_id, "current": current, "total": total},
            )

        try:
            new_message_id = await self.response_formatter.safe_reply_with_id(
                message, progress_text
            )
        except Exception as send_error:  # noqa: BLE001
            logger.warning(
                "progress_update_send_failed",
                extra={
                    "error": str(send_error),
                    "current": current,
                    "total": total,
                    "message_id": message_id,
                },
            )
            return message_id

        if new_message_id is None:
            logger.debug(
                "progress_update_sent_without_id",
                extra={
                    "current": current,
                    "total": total,
                    "text_length": len(progress_text),
                    "previous_message_id": message_id,
                },
            )
        else:
            logger.debug(
                "progress_update_sent",
                extra={
                    "current": current,
                    "total": total,
                    "message_id": new_message_id,
                    "text_length": len(progress_text),
                },
            )

        return new_message_id

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

        try:
            interaction_id = self.db.insert_user_interaction(
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

    def _should_notify_rate_limit(self, uid: int) -> bool:
        """Determine if we should notify a user about rate limiting."""
        now = time.time()
        deadline = self._rate_limit_notified_until.get(uid, 0.0)
        if now >= deadline:
            self._rate_limit_notified_until[uid] = now + self._rate_limit_notice_window
            return True
        logger.debug(
            "rate_limit_notice_suppressed",
            extra={
                "uid": uid,
                "remaining_suppression": max(0.0, deadline - now),
            },
        )
        return False

    def _is_duplicate_message(self, message_key: tuple[int, int, int], text_signature: str) -> bool:
        """Return True if we've processed this message recently."""
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
