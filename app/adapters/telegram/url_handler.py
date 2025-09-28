"""URL handling for Telegram bot messages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class URLHandler:
    """Handles URL-related message processing and state management."""

    def __init__(
        self,
        db: Database,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
    ) -> None:
        self.db = db
        self.response_formatter = response_formatter
        self.url_processor = url_processor

        # Simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # Pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}

    def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        self._awaiting_url_users.add(uid)

    def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        """Add user to pending multi-links confirmation."""
        self._pending_multi_links[uid] = urls

    def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL or multi-link confirmation requests for a user."""
        awaiting_cancelled = uid in self._awaiting_url_users
        if awaiting_cancelled:
            self._awaiting_url_users.discard(uid)

        multi_cancelled = uid in self._pending_multi_links
        if multi_cancelled:
            self._pending_multi_links.pop(uid, None)

        return awaiting_cancelled, multi_cancelled

    async def handle_awaited_url(
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
            await self._request_multi_link_confirmation(
                message, uid, urls, interaction_id, start_time
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

    async def handle_direct_url(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle direct URL message with security validation."""
        urls = extract_all_urls(text)

        # Security check: limit batch size
        if len(urls) > self.response_formatter.MAX_BATCH_URLS:
            await self.response_formatter.safe_reply(
                message,
                f"❌ Too many URLs ({len(urls)}). Maximum allowed: {self.response_formatter.MAX_BATCH_URLS}.",
            )
            logger.warning(
                "direct_url_batch_limit_exceeded",
                extra={
                    "url_count": len(urls),
                    "max_allowed": self.response_formatter.MAX_BATCH_URLS,
                    "uid": uid,
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
                logger.warning(
                    "invalid_direct_url", extra={"url": url, "error": error_msg, "uid": uid}
                )

        if not valid_urls:
            await self.response_formatter.safe_reply(
                message, "❌ No valid URLs found after security checks."
            )
            return

        urls = valid_urls

        if len(urls) > 1:
            await self._request_multi_link_confirmation(
                message, uid, urls, interaction_id, start_time
            )
            return

        if len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )

    async def handle_multi_link_confirmation(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle yes/no confirmation for multiple links with optimized parallel processing."""
        normalized = self._normalize_response(text)

        if self._is_affirmative(normalized):
            urls = self._pending_multi_links.get(uid)
            if not urls:
                logger.warning(
                    "multi_confirm_missing_state", extra={"uid": uid, "cid": correlation_id}
                )
                await self.response_formatter.safe_reply(
                    message,
                    "ℹ️ No pending multi-link request to confirm. Please send the links again.",
                )
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_missing",
                        error_occurred=True,
                        error_message="no_pending_multi_links",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                return

            if not isinstance(urls, list) or any(
                not isinstance(url, str) or not url.strip() for url in urls
            ):
                logger.warning(
                    "multi_confirm_invalid_state",
                    extra={
                        "uid": uid,
                        "cid": correlation_id,
                        "type": type(urls).__name__,
                        "count": len(urls) if isinstance(urls, list) else None,
                    },
                )
                # Drop the corrupted state to avoid repeated failures
                self._pending_multi_links.pop(uid, None)
                await self.response_formatter.safe_reply(
                    message,
                    "❌ Pending multi-link request is invalid. Please send the links again.",
                )
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_invalid",
                        error_occurred=True,
                        error_message="invalid_multi_link_cache",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                return

            # State is valid; remove it before processing to prevent double handling
            self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(
                message, f"🚀 Processing {len(urls)} links in parallel..."
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="processing",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

            # Process URLs in parallel with controlled concurrency
            await self._process_multiple_urls_parallel(message, urls, uid, correlation_id)
            return

        if self._is_negative(normalized):
            self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(message, "Cancelled.")
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL."""
        return uid in self._awaiting_url_users

    def has_pending_multi_links(self, uid: int) -> bool:
        """Check if user has pending multi-link confirmation."""
        return uid in self._pending_multi_links

    def _normalize_response(self, text: str) -> str:
        return text.strip().lower()

    def _is_affirmative(self, text: str) -> bool:
        """Check if text is an affirmative response."""
        return text in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        """Check if text is a negative response."""
        return text in {"n", "no", "-", "cancel", "stop", "нет", "не"}

    async def _request_multi_link_confirmation(
        self,
        message: Any,
        uid: int,
        urls: list[str],
        interaction_id: int,
        start_time: float,
    ) -> None:
        self._pending_multi_links[uid] = urls
        await self.response_formatter.safe_reply(message, f"Process {len(urls)} links? (yes/no)")
        logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="confirmation",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _process_multiple_urls_parallel(
        self,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
    ) -> None:
        """Process multiple URLs in parallel with controlled concurrency."""
        if not urls:
            return

        # Use semaphore to limit concurrent processing (prevent overwhelming external APIs)
        semaphore = asyncio.Semaphore(
            min(3, len(urls))
        )  # Max 3 concurrent URLs for user-initiated batches

        # Thread-safe progress tracking with proper isolation
        class ThreadSafeProgress:
            def __init__(
                self, total: int, message: Any, progress_msg_id: int | None, response_formatter
            ):
                self.total = total
                self._completed = 0
                self._lock = asyncio.Lock()
                self._last_update = 0.0
                self._last_displayed = 0
                self.update_interval = 1.0  # Update every 1 second minimum
                self.message = message
                self.progress_msg_id = progress_msg_id
                self.response_formatter = response_formatter
                self._update_queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue(maxsize=1)

            async def increment_and_update(self) -> tuple[int, int]:
                """Atomically increment counter and queue progress update if needed."""
                # Fast path: only increment counter under lock
                async with self._lock:
                    self._completed += 1
                    current_time = time.time()

                    # Check if we should update (don't call external methods in lock)
                    progress_threshold = max(1, self.total // 20)  # Update every 5% or 1 URL
                    # For small batches, be more responsive - update every URL
                    if self.total <= 5:
                        progress_threshold = 1

                    # Check both time and progress thresholds
                    time_threshold_met = current_time - self._last_update >= self.update_interval
                    progress_threshold_met = (
                        self._completed - self._last_displayed >= progress_threshold
                    )

                    # For small batches, prioritize progress threshold over time threshold
                    should_update = (time_threshold_met and progress_threshold_met) or (
                        self.total <= 5 and progress_threshold_met
                    )

                    # Debug logging to understand progress tracking
                    logger.debug(
                        "progress_tracking_debug",
                        extra={
                            "completed": self._completed,
                            "total": self.total,
                            "threshold": progress_threshold,
                            "should_update": should_update,
                            "time_diff": current_time - self._last_update,
                            "update_interval": self.update_interval,
                            "last_displayed": self._last_displayed,
                            "time_threshold_met": time_threshold_met,
                            "progress_threshold_met": progress_threshold_met,
                        },
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
                        logger.debug(
                            "progress_update_queued",
                            extra={"completed": completed, "total": self.total},
                        )
                    except asyncio.QueueFull:
                        logger.debug("progress_update_queue_full", extra={"completed": completed})
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
                            percentage = int((completed / total) * 100)
                            progress_text = f"🔄 Processing {total} links in parallel: {completed}/{total} ({percentage}%)"

                            logger.debug(
                                "attempting_progress_update",
                                extra={
                                    "completed": completed,
                                    "total": total,
                                    "progress_text": progress_text,
                                    "progress_msg_id": self.progress_msg_id,
                                },
                            )

                            chat_id = getattr(self.message.chat, "id", None)
                            if chat_id and self.progress_msg_id:
                                await self.response_formatter.edit_message(
                                    chat_id, self.progress_msg_id, progress_text
                                )
                                logger.debug(
                                    "progress_update_sent_successfully",
                                    extra={
                                        "completed": completed,
                                        "total": total,
                                        "chat_id": chat_id,
                                        "message_id": self.progress_msg_id,
                                    },
                                )
                            else:
                                logger.warning(
                                    "progress_update_skipped",
                                    extra={
                                        "chat_id": chat_id,
                                        "progress_msg_id": self.progress_msg_id,
                                        "reason": "missing_chat_id_or_msg_id",
                                    },
                                )
                        except Exception as e:
                            logger.warning(
                                "progress_update_failed",
                                extra={
                                    "error": str(e),
                                    "completed": completed,
                                    "total": total,
                                    "progress_msg_id": self.progress_msg_id,
                                },
                            )
                except TimeoutError:
                    pass  # No more updates to process

        async def process_single_url(
            url: str, progress_tracker: ThreadSafeProgress
        ) -> tuple[str, bool, str]:
            """Process a single URL and return (url, success, error_message)."""
            async with semaphore:
                per_link_cid = generate_correlation_id()
                logger.debug(
                    "processing_link_parallel",
                    extra={"uid": uid, "url": url, "cid": per_link_cid},
                )

                try:
                    # Add timeout protection for individual URL processing
                    await asyncio.wait_for(
                        self.url_processor.handle_url_flow(
                            message, url, correlation_id=per_link_cid
                        ),
                        timeout=600,  # 10 minute timeout per URL
                    )

                    # Update progress after successful completion
                    await progress_tracker.increment_and_update()

                    return url, True, ""
                except TimeoutError:
                    error_msg = "Timeout processing URL after 10 minutes"
                    logger.error(
                        "parallel_url_processing_timeout",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg, "uid": uid},
                    )
                    # Update progress even on timeout
                    await progress_tracker.increment_and_update()

                    return url, False, error_msg
                except Exception as e:
                    # Enhanced error handling with transient failure detection
                    error_msg = str(e)
                    transient_keywords = ["timeout", "connection", "network", "rate limit"]
                    if any(keyword in error_msg.lower() for keyword in transient_keywords):
                        logger.warning(
                            "transient_error_detected",
                            extra={"url": url, "cid": per_link_cid, "error": error_msg, "uid": uid},
                        )
                        # Could implement retry logic here in the future

                    logger.error(
                        "parallel_url_processing_failed",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg, "uid": uid},
                    )

                    # Update progress even on failure
                    await progress_tracker.increment_and_update()

                    return url, False, error_msg

        # Send initial progress message with error handling
        try:
            initial_progress_text = (
                f"🔄 Processing {len(urls)} links in parallel: 0/{len(urls)} (0%)"
            )
            progress_msg_id = await self.response_formatter.safe_reply_with_id(
                message, initial_progress_text
            )
            logger.debug(
                "initial_progress_message_created",
                extra={
                    "progress_msg_id": progress_msg_id,
                    "url_count": len(urls),
                    "progress_text": initial_progress_text,
                    "uid": uid,
                },
            )
        except Exception as e:
            logger.warning(
                "failed_to_create_progress_message",
                extra={"error": str(e), "uid": uid, "url_count": len(urls)},
            )
            progress_msg_id = None

        # Create progress tracker
        progress_tracker = ThreadSafeProgress(
            len(urls), message, progress_msg_id, self.response_formatter
        )

        # Initialize counters for result tracking
        successful = 0
        failed = 0
        failed_urls = []

        # Process URLs in memory-efficient batches to prevent resource exhaustion
        # User-initiated batches use smaller batches for better responsiveness and user control
        batch_size = min(5, len(urls))  # Process max 5 URLs at a time for user-initiated batches

        async def process_batches():
            """Process URL batches with progress tracking."""
            nonlocal successful, failed, failed_urls
            for batch_start in range(0, len(urls), batch_size):
                batch_end = min(batch_start + batch_size, len(urls))
                batch_urls = urls[batch_start:batch_end]

                # Create tasks for this batch only
                batch_tasks = [process_single_url(url, progress_tracker) for url in batch_urls]

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
                        failed += 1
                        logger.error(
                            "unexpected_task_exception", extra={"error": str(result), "uid": uid}
                        )
                        failed_urls.append(f"Unknown URL (task exception: {type(result).__name__})")
                    elif isinstance(result, tuple) and len(result) == 3:
                        url, success, error_msg = result
                        if success:
                            successful += 1
                        else:
                            failed += 1
                            failed_urls.append(url)
                            if error_msg:
                                logger.debug(
                                    "url_processing_failed_detail",
                                    extra={"url": url, "error": error_msg, "uid": uid},
                                )
                    elif isinstance(result, tuple) and len(result) == 2:
                        # Backward compatibility with old format
                        url, success = result
                        if success:
                            successful += 1
                        else:
                            failed += 1
                            failed_urls.append(url)
                            logger.warning("legacy_result_format", extra={"url": url, "uid": uid})
                    else:
                        # Unexpected result type - this is a programming error
                        failed += 1
                        logger.error(
                            "unexpected_result_type",
                            extra={
                                "result_type": type(result).__name__,
                                "result_value": str(result)[:200],  # Truncate for logging
                                "uid": uid,
                            },
                        )
                        failed_urls.append(
                            f"Unknown URL (unexpected result type: {type(result).__name__})"
                        )

                # Small delay between batches to prevent overwhelming external APIs
                if batch_end < len(urls):
                    await asyncio.sleep(0.1)

        # Run batch processing and progress updates concurrently
        await asyncio.gather(
            process_batches(), progress_tracker.process_update_queue(), return_exceptions=True
        )

        # Send completion summary with detailed feedback
        if failed == 0:
            await self.response_formatter.safe_reply(
                message, f"✅ Successfully processed all {successful} links!"
            )
        elif successful > 0:
            # Partial success - provide helpful feedback
            failure_rate = (failed / len(urls)) * 100
            if failure_rate <= 20:  # Less than 20% failed
                message_text = (
                    f"✅ Processed {successful}/{len(urls)} links successfully! "
                    f"({failed} failed - likely temporary issues)"
                )
            else:
                message_text = (
                    f"⚠️ Processed {successful}/{len(urls)} links successfully. "
                    f"{failed} failed. Some URLs may be inaccessible or invalid."
                )
            await self.response_formatter.safe_reply(message, message_text)
        else:
            # Complete failure
            await self.response_formatter.safe_reply(
                message,
                "❌ Failed to process any links. Please check if URLs are valid and accessible.",
            )

        # Safety check: ensure all URLs were processed
        expected_total = len(urls)
        actual_total = successful + failed

        if actual_total != expected_total:
            logger.error(
                "parallel_processing_count_mismatch",
                extra={
                    "uid": uid,
                    "expected_total": expected_total,
                    "actual_total": actual_total,
                    "successful": successful,
                    "failed": failed,
                },
            )

        logger.info(
            "parallel_processing_complete",
            extra={
                "uid": uid,
                "total": expected_total,
                "successful": successful,
                "failed": failed,
                "failed_urls": failed_urls[:3],  # Log first 3 failed URLs
                "count_match": actual_total == expected_total,
            },
        )

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

        if interaction_id <= 0:
            return

        try:
            self.db.update_user_interaction(
                interaction_id=interaction_id,
                response_sent=response_sent,
                response_type=response_type,
                error_occurred=error_occurred,
                error_message=error_message,
                processing_time_ms=processing_time_ms,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "user_interaction_update_failed",
                extra={"interaction_id": interaction_id, "error": str(exc)},
            )
