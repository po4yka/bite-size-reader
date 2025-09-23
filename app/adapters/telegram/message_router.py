"""Message routing and coordination for Telegram bot."""
# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls, looks_like_url
from app.db.database import Database
from app.models.telegram.telegram_models import TelegramMessage

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
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.access_controller = access_controller
        self.command_processor = command_processor
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.response_formatter = response_formatter
        self._audit = audit_func

        # Store reference to URL processor for silent processing
        self._url_processor = url_handler.url_processor

    async def route_message(self, message: Any) -> None:
        """Main message routing entry point."""
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

            # Route message based on content
            await self._route_message_content(
                message, text, uid, has_forward, correlation_id, interaction_id, start_time
            )

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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(e)[:500],  # Limit error message length
                    processing_time_ms=int((time.time() - start_time) * 1000),
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

        if text.startswith("/unread"):
            await self.command_processor.handle_unread_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return

        if text.startswith("/read"):
            await self.command_processor.handle_read_command(
                message, text, uid, correlation_id, interaction_id, start_time
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

        # Handle forwarded messages
        if getattr(message, "forward_from_chat", None) and getattr(
            message, "forward_from_message_id", None
        ):
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
        try:
            # Download and parse the file
            file_path = await self._download_file(message)
            if not file_path:
                await self.response_formatter.safe_reply(message, "Failed to download the file.")
                return

            # Parse URLs from the file
            urls = self._parse_txt_file(file_path)
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
        """Parse URLs from .txt file."""
        urls = []
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and line.startswith("http"):
                        urls.append(line)
        except Exception as e:
            logger.error("file_parse_error", extra={"error": str(e), "file_path": file_path})
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
        semaphore = asyncio.Semaphore(min(5, total))  # Max 5 concurrent URLs

        # Circuit breaker: if too many failures in a chunk, reduce concurrency
        max_concurrent_failures = min(
            10, total // 3
        )  # Allow up to 1/3 failures before reducing concurrency

        async def process_single_url(url: str) -> tuple[str, bool, str]:
            """Process a single URL and return (url, success, error_message)."""
            async with semaphore:
                per_link_cid = generate_correlation_id()
                logger.info(
                    "processing_url_from_file",
                    extra={"url": url, "cid": per_link_cid},
                )

                try:
                    # Add timeout protection for individual URL processing
                    await asyncio.wait_for(
                        self._process_url_silently(message, url, per_link_cid, interaction_id),
                        timeout=600,  # 10 minute timeout per URL
                    )

                    # Update progress after successful completion
                    await progress_tracker.increment_and_update()
                    return url, True, ""
                except asyncio.TimeoutError:
                    error_msg = "Timeout processing URL after 10 minutes"
                    logger.error(
                        "url_processing_timeout",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg},
                    )
                    # Update progress even on timeout
                    await progress_tracker.increment_and_update()
                    return url, False, error_msg
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
        completed = 0
        successful = 0
        failed_urls = []

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

            async def increment_and_update(self) -> tuple[int, int]:
                """Atomically increment counter and queue progress update if needed."""
                # Fast path: only increment counter under lock
                async with self._lock:
                    self._completed += 1
                    current_time = time.time()

                    # Check if we should update (don't call external methods in lock)
                    progress_threshold = max(1, self.total // 20)  # Update every 5% or 1 URL
                    should_update = (
                        current_time - self._last_update >= self.update_interval
                        and self._completed - self._last_displayed >= progress_threshold
                    )

                    if should_update:
                        self._last_update = current_time
                        self._last_displayed = self._completed

                    completed = self._completed

                # Slow path: call external method outside lock to prevent deadlocks
                if should_update:
                    try:
                        # Non-blocking queue put - if full, skip this update
                        self._update_queue.put_nowait((completed, self.total))
                    except asyncio.QueueFull:
                        pass  # Skip if update queue is full (prevents blocking)

                return completed, self.total

            async def process_update_queue(self) -> None:
                """Process queued progress updates outside of locks."""
                try:
                    while True:
                        completed, total = await asyncio.wait_for(
                            self._update_queue.get(), timeout=0.1
                        )
                        try:
                            await self.message_router._send_progress_update(
                                self.message, completed, total, self.progress_message_id
                            )
                        except Exception as e:
                            logger.warning(
                                "progress_update_failed",
                                extra={
                                    "error": str(e),
                                    "completed": completed,
                                    "total": total,
                                },
                            )
                except asyncio.TimeoutError:
                    pass  # No more updates to process

        progress_tracker = ThreadSafeProgress(total, message, progress_message_id, self)

        # Process URLs in true memory-efficient batches
        # File processing can use larger batches since users expect bulk processing
        batch_size = min(10, total)  # Process max 10 URLs at a time to limit memory

        async def process_batches():
            """Process URL batches with progress tracking."""
            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_urls = urls[batch_start:batch_end]

                # Create tasks for this batch only
                batch_tasks = [process_single_url(url) for url in batch_urls]

                # Process batch and handle results immediately
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Process results from this batch immediately
                for result in batch_results:
                    # Progress is already incremented in process_single_url() - no double counting

                    if isinstance(result, Exception):
                        # Handle asyncio-specific exceptions properly
                        if isinstance(result, asyncio.CancelledError):
                            # Re-raise cancellation
                            raise result
                        # This should rarely happen due to return_exceptions=True, but handle it
                        logger.error(
                            "unexpected_task_exception",
                            extra={"error": str(result), "cid": correlation_id},
                        )
                        failed_urls.append(f"Unknown URL (task exception: {type(result).__name__})")
                    elif isinstance(result, tuple) and len(result) == 3:
                        url, success, error_msg = result
                        if success:
                            successful += 1
                        else:
                            failed_urls.append(url)
                            if error_msg:
                                logger.debug(
                                    "url_processing_failed_detail",
                                    extra={"url": url, "error": error_msg, "cid": correlation_id},
                                )
                    elif isinstance(result, tuple) and len(result) == 2:
                        # Backward compatibility with old format
                        url, success = result
                        if success:
                            successful += 1
                        else:
                            failed_urls.append(url)
                            logger.warning(
                                "legacy_result_format", extra={"url": url, "cid": correlation_id}
                            )
                    else:
                        # Unexpected result type - this is a programming error
                        logger.error(
                            "unexpected_result_type",
                            extra={
                                "result_type": type(result).__name__,
                                "result_value": str(result)[:200],  # Truncate for logging
                                "cid": correlation_id,
                            },
                        )
                        failed_urls.append(
                            f"Unknown URL (unexpected result type: {type(result).__name__})"
                        )

            # Small delay between batches to prevent overwhelming external APIs
            if batch_end < total:
                await asyncio.sleep(0.1)

        # Run batch processing and progress updates concurrently
        await asyncio.gather(
            process_batches(), progress_tracker.process_update_queue(), return_exceptions=True
        )

        # Final progress update to ensure 100% completion is shown
        try:
            await self._send_progress_update(message, total, total, progress_message_id)
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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="batch_processing_complete",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _process_url_silently(
        self,
        message: Any,
        url: str,
        correlation_id: str,
        interaction_id: int,
    ) -> None:
        """Process a single URL without sending Telegram responses."""
        try:
            # Call the URL processor's handle_url_flow method with silent=True
            await self._url_processor.handle_url_flow(
                message,
                url,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                silent=True,
            )
        except Exception as e:
            logger.error(
                "url_processing_failed",
                extra={"url": url, "cid": correlation_id, "error": str(e)},
            )

    async def _send_progress_update(
        self, message: Any, current: int, total: int, message_id: int | None = None
    ) -> None:
        """Send progress update, editing existing message if message_id provided, otherwise send as new message."""
        try:
            # Create enhanced progress bar with percentage
            progress_bar = self._create_progress_bar(current, total)
            percentage = int((current / total) * 100) if total > 0 else 0
            progress_text = (
                f"🔄 Processing links: {current}/{total} ({percentage}%)\n{progress_bar}"
            )

            if message_id is not None:
                # Edit existing message
                chat_id = getattr(message.chat, "id", None)
                if chat_id is not None:
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
                else:
                    logger.warning("progress_update_no_chat_id", extra={"message_id": message_id})
                    # Fallback to new message
                    await self.response_formatter.safe_reply(message, progress_text)
            else:
                # Send as new message (fallback)
                await self.response_formatter.safe_reply(message, progress_text)
                logger.debug(
                    "progress_update_sent",
                    extra={"current": current, "total": total, "text_length": len(progress_text)},
                )
        except Exception as e:
            logger.warning(
                "progress_update_failed",
                extra={
                    "error": str(e),
                    "current": current,
                    "total": total,
                    "message_id": message_id,
                },
            )

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
            extra={"interaction_id": interaction_id, "response_type": response_type},
        )
