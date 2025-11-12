"""Message routing and coordination for Telegram bot."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction
from app.models.telegram.telegram_models import TelegramMessage
from app.security.file_validation import FileValidationError, SecureFileValidator
from app.security.rate_limiter import RateLimitConfig, UserRateLimiter

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.access_controller import AccessController
    from app.adapters.telegram.command_processor import CommandProcessor
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.url_handler import URLHandler

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
        self._rate_limiter = UserRateLimiter(
            RateLimitConfig(
                max_requests=10,  # 10 requests per window
                window_seconds=60,  # 60 second window
                max_concurrent=3,  # Max 3 concurrent operations per user
                cooldown_multiplier=2.0,  # 2x window cooldown after limit
            )
        )
        self._file_validator = SecureFileValidator(
            max_file_size=10 * 1024 * 1024  # 10 MB max file size
        )

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
                logger.warning(f"Invalid user ID type: {type(uid)}, skipping message processing")
                await self.response_formatter.safe_reply(
                    message, "Unable to determine user identity. Message processing skipped."
                )
                return

            logger.info(f"Checking access for UID: {uid} (type: {type(uid)})")
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
            if not await self.access_controller.check_access(
                uid, message, correlation_id, interaction_id, start_time
            ):
                return

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
            except Exception:
                pass
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

    async def handle_multi_confirm_response(
        self, message: Any, uid: int, response: str
    ) -> None:
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
        # Commands
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
                self.url_handler.add_pending_multi_links(uid, extract_all_urls(text))
            elif action == "awaiting_url":
                self.url_handler.add_awaiting_user(uid)
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
        if self.url_handler.is_awaiting_url(uid) and looks_like_url(text):
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
        if self.url_handler.has_pending_multi_links(uid):
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
                f"🔄 Processing links: 0/{len(urls)}\n{self._create_progress_bar(0, len(urls))}",
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
            # Clean up downloaded file
            if file_path:
                try:
                    self._file_validator.cleanup_file(file_path)
                except Exception as e:
                    logger.debug(
                        "file_cleanup_error",
                        extra={"error": str(e), "file_path": file_path, "cid": correlation_id},
                    )

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
            List of URLs found in file

        Raises:
            FileValidationError: If file validation fails
        """
        # Use secure file validator to read file
        lines = self._file_validator.safe_read_text_file(file_path)

        # Extract URLs from lines
        urls = []
        for line in lines:
            line = line.strip()
            # Basic URL validation - starts with http/https
            if line and (line.startswith("http://") or line.startswith("https://")):
                # Additional validation: check for suspicious patterns
                if " " not in line and "\t" not in line:  # No spaces/tabs in URL
                    urls.append(line)
                else:
                    logger.warning(
                        "suspicious_url_skipped",
                        extra={"url_preview": line[:50], "reason": "contains whitespace"},
                    )

        logger.info(
            "file_parsed_successfully",
            extra={"file_path": file_path, "urls_found": len(urls), "lines_read": len(lines)},
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
        # Note: Combined with batch processing, this limits both memory usage and API load
        # Semaphore should allow at least as many concurrent URLs as batch size
        semaphore = asyncio.Semaphore(min(20, total))  # Max 20 concurrent URLs

        # Circuit breaker: if too many failures in a chunk, reduce concurrency
        max_concurrent_failures = min(
            10, total // 3
        )  # Allow up to 1/3 failures before reducing concurrency

        async def process_single_url(
            url: str, progress_tracker: ThreadSafeProgress
        ) -> tuple[str, bool, str]:
            """Process a single URL and return (url, success, error_message)."""
            async with semaphore:
                per_link_cid = generate_correlation_id()
                logger.info(
                    "processing_url_from_file",
                    extra={"url": url, "cid": per_link_cid},
                )

                try:
                    # Add timeout protection for individual URL processing
                    success = await asyncio.wait_for(
                        self._process_url_silently(message, url, per_link_cid, interaction_id),
                        timeout=600,  # 10 minute timeout per URL
                    )

                    # Update progress after completion (success or failure)
                    await progress_tracker.increment_and_update()

                    if success:
                        logger.debug(
                            "process_single_url_success",
                            extra={"url": url, "cid": per_link_cid, "result": "success"},
                        )
                        return url, True, ""
                    else:
                        logger.debug(
                            "process_single_url_failure",
                            extra={"url": url, "cid": per_link_cid, "result": "failed"},
                        )
                        return url, False, "URL processing failed"
                except asyncio.TimeoutError:
                    error_msg = "Timeout processing URL after 10 minutes"
                    logger.error(
                        "url_processing_timeout",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg},
                    )
                    # Update progress even on timeout
                    await progress_tracker.increment_and_update()
                    return url, False, error_msg
                except asyncio.CancelledError:
                    # Re-raise cancellation to stop all processing
                    raise
                except Exception as e:
                    error_msg = str(e)
                    logger.error(
                        "url_processing_failed",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg},
                    )
                    # Update progress even on failure
                    await progress_tracker.increment_and_update()
                    return url, False, error_msg

        # Process URLs in parallel with controlled concurrency and memory optimization
        # For very large batches (>30 URLs), process in chunks to manage memory
        chunk_size = 30 if total > 30 else total
        # Variables will be set from batch processing results

        # Thread-safe progress tracking with proper isolation
        class ThreadSafeProgress:
            def __init__(
                self, total: int, message: Any, progress_message_id: int | None, message_router
            ):
                self.total = total
                self._completed = 0
                self._lock = asyncio.Lock()
                self._last_update = 0.0
                self._last_displayed = 0
                self.update_interval = 1.0  # Update every 1 second minimum
                self.message = message
                self.progress_message_id = progress_message_id
                self.message_router = message_router
                self._update_queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue(maxsize=1)
                self._queue_overflow_logged = False
                self._shutdown_event = asyncio.Event()

            async def increment_and_update(self) -> tuple[int, int]:
                """Atomically increment counter and queue progress update if needed."""
                # Fast path: only increment counter under lock
                async with self._lock:
                    self._completed += 1
                    current_time = time.time()

                    # Check if we should update (don't call external methods in lock)
                    progress_threshold = max(1, self.total // 20)  # Update every 5% or 1 URL
                    # For small batches, be more responsive - update every URL
                    if self.total <= 10:  # File processing uses larger batches
                        progress_threshold = 1

                    # Check both time and progress thresholds
                    time_threshold_met = current_time - self._last_update >= self.update_interval
                    progress_threshold_met = (
                        self._completed - self._last_displayed >= progress_threshold
                    )

                    # Only enqueue updates if we actually made forward progress
                    made_progress = self._completed > self._last_displayed
                    should_update = False
                    if made_progress:
                        # Always surface meaningful progress jumps immediately
                        if progress_threshold_met:
                            should_update = True
                        # Otherwise, send periodic heartbeats while work is ongoing
                        elif time_threshold_met:
                            should_update = True
                        # For very small batches we already handle every increment above

                    if should_update:
                        self._last_update = current_time
                        self._last_displayed = self._completed

                    completed = self._completed

                # Slow path: call external method outside lock to prevent deadlocks
                if should_update:
                    try:
                        self._update_queue.put_nowait((completed, self.total))
                        self._queue_overflow_logged = False
                    except asyncio.QueueFull:
                        try:
                            dropped_update = self._update_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            dropped_update = None
                        else:
                            self._update_queue.task_done()

                        if not self._queue_overflow_logged:
                            logger.debug(
                                "progress_update_queue_full",
                                extra={
                                    "last_displayed": self._last_displayed,
                                    "completed": completed,
                                    "dropped": dropped_update,
                                },
                            )
                            self._queue_overflow_logged = True

                        self._update_queue.put_nowait((completed, self.total))

                if completed >= self.total:
                    self._shutdown_event.set()

                return completed, self.total

            async def process_update_queue(self) -> None:
                """Process queued progress updates outside of locks."""
                while True:
                    if self._shutdown_event.is_set() and self._update_queue.empty():
                        break

                    try:
                        completed, total = await asyncio.wait_for(
                            self._update_queue.get(), timeout=0.5
                        )
                    except asyncio.TimeoutError:
                        continue

                    try:
                        new_message_id = await self.message_router._send_progress_update(
                            self.message, completed, total, self.progress_message_id
                        )
                        if new_message_id is not None:
                            self.progress_message_id = new_message_id
                    except Exception as e:
                        logger.warning(
                            "progress_update_failed",
                            extra={
                                "error": str(e),
                                "completed": completed,
                                "total": total,
                            },
                        )
                    finally:
                        self._update_queue.task_done()

            def mark_complete(self) -> None:
                """Signal that no further updates will be enqueued."""
                self._shutdown_event.set()

        progress_tracker = ThreadSafeProgress(total, message, progress_message_id, self)

        # Process URLs in true memory-efficient batches
        # File processing can use larger batches since users expect bulk processing
        batch_size = min(5, total)  # Process max 5 URLs at a time to limit memory and API load

        async def process_batches():
            """Process URL batches with progress tracking."""
            batch_successful = 0
            batch_failed = 0
            batch_failed_urls = []

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
                            f"Unknown URL (task exception: {type(result).__name__})"
                        )
                    elif isinstance(result, tuple) and len(result) == 3:
                        url, success, error_msg = result
                        if success:
                            batch_successful += 1
                        else:
                            batch_failed += 1
                            batch_failed_urls.append(url)
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
                            batch_failed_urls.append(url)
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
                            f"Unknown URL (unexpected result type: {type(result).__name__})"
                        )

            # Small delay between batches to prevent overwhelming external APIs
            if batch_end < total:
                await asyncio.sleep(0.1)

            return batch_successful, batch_failed, batch_failed_urls

        # Run batch processing and progress updates concurrently
        progress_task = asyncio.create_task(progress_tracker.process_update_queue())
        batch_result: tuple[int, int, list[str]] | Exception
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
            logger.error(
                "batch_processing_failed",
                extra={"error": str(batch_result), "cid": correlation_id},
            )
            # Set default values if batch processing failed
            successful = 0
            failed = total
            completed = total
            failed_urls = [f"Batch processing failed: {str(batch_result)}"]
        elif isinstance(batch_result, tuple) and len(batch_result) == 3:
            # Unpack the results from process_batches()
            successful, failed, failed_urls = batch_result
            completed = successful + failed
        else:
            # Unexpected result type
            logger.error(
                "unexpected_batch_result_type",
                extra={"result_type": type(batch_result).__name__, "cid": correlation_id},
            )
            successful = 0
            failed = total
            completed = total
            failed_urls = [f"Unexpected batch result type: {type(batch_result).__name__}"]

        # Final progress update to ensure 100% completion is shown
        try:
            final_message_id = await self._send_progress_update(
                message, total, total, progress_tracker.progress_message_id
            )
            if final_message_id is not None:
                progress_tracker.progress_message_id = final_message_id
        except Exception as e:
            logger.warning("final_progress_update_failed", extra={"error": str(e)})

        # Send completion message with statistics
        logger.debug(
            "sending_completion_message",
            extra={"url_count": total, "successful": successful, "failed": len(failed_urls)},
        )

        # Create completion message with statistics
        completion_message = f"✅ Processing complete!\n"
        completion_message += f"📊 Total: {total} links\n"
        completion_message += f"✅ Successful: {successful}\n"
        if failed_urls:
            completion_message += f"❌ Failed: {len(failed_urls)}"

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
    ) -> bool:
        """Process a single URL without sending Telegram responses.

        Returns:
            bool: True if processing succeeded, False if it failed
        """
        try:
            # Call the URL processor's handle_url_flow method with silent=True
            await self._url_processor.handle_url_flow(
                message,
                url,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                silent=True,
            )
            return True
        except Exception as e:
            logger.error(
                "url_processing_failed",
                extra={"url": url, "cid": correlation_id, "error": str(e)},
            )
            return False

    async def _send_progress_update(
        self, message: Any, current: int, total: int, message_id: int | None = None
    ) -> int | None:
        """Send or edit the Telegram progress message.

        Returns the message ID that should be used for subsequent edits when available.
        """

        progress_bar = self._create_progress_bar(current, total)
        percentage = int((current / total) * 100) if total > 0 else 0
        progress_text = f"🔄 Processing links: {current}/{total} ({percentage}%)\n{progress_bar}"

        chat_id = getattr(message.chat, "id", None)

        if message_id is not None and chat_id is not None:
            try:
                await self.response_formatter.edit_message(chat_id, message_id, progress_text)
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
            except Exception as edit_error:  # noqa: BLE001
                error_text = str(edit_error)
                if "message is not modified" in error_text.lower():
                    logger.debug(
                        "progress_update_unchanged",
                        extra={
                            "current": current,
                            "total": total,
                            "message_id": message_id,
                        },
                    )
                    return message_id

                logger.warning(
                    "progress_update_edit_failed",
                    extra={
                        "error": error_text,
                        "current": current,
                        "total": total,
                        "message_id": message_id,
                    },
                )
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

    def _create_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """Create a simple text progress bar."""
        filled = int(width * current / total)
        empty = width - filled
        return "█" * filled + "░" * empty

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
