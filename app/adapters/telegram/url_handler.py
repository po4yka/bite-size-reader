"""URL handling for Telegram bot messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls
from app.db.user_interactions import async_safe_update_user_interaction
from app.utils.message_formatter import format_completion_message, format_progress_message
from app.utils.progress_tracker import ProgressTracker

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.db.database import Database

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

        # Lock to protect shared state from concurrent access
        self._state_lock = asyncio.Lock()
        # Simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # Pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}

    async def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        async with self._state_lock:
            self._awaiting_url_users.add(uid)

    async def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        """Add user to pending multi-links confirmation."""
        async with self._state_lock:
            self._pending_multi_links[uid] = urls

    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL or multi-link confirmation requests for a user."""
        async with self._state_lock:
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
        async with self._state_lock:
            self._awaiting_url_users.discard(uid)

        urls = await self._apply_url_security_checks(message, urls, uid)
        if not urls:
            return

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
        urls = await self._apply_url_security_checks(message, urls, uid)
        if not urls:
            return

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
            async with self._state_lock:
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
                    await async_safe_update_user_interaction(
                        self.db,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_missing",
                        error_occurred=True,
                        error_message="no_pending_multi_links",
                        start_time=start_time,
                        logger_=logger,
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
                async with self._state_lock:
                    self._pending_multi_links.pop(uid, None)
                await self.response_formatter.safe_reply(
                    message,
                    "❌ Pending multi-link request is invalid. Please send the links again.",
                )
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.db,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_invalid",
                        error_occurred=True,
                        error_message="invalid_multi_link_cache",
                        start_time=start_time,
                        logger_=logger,
                    )
                return

            # State is valid; remove it before processing to prevent double handling
            async with self._state_lock:
                self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(
                message, f"🚀 Processing {len(urls)} links in parallel..."
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="processing",
                    start_time=start_time,
                    logger_=logger,
                )

            # Process URLs in parallel with controlled concurrency
            await self._process_multiple_urls_parallel(message, urls, uid, correlation_id)
            return

        if self._is_negative(normalized):
            async with self._state_lock:
                self._pending_multi_links.pop(uid, None)
            await self.response_formatter.safe_reply(message, "Cancelled.")
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    start_time=start_time,
                    logger_=logger,
                )

    async def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL."""
        async with self._state_lock:
            return uid in self._awaiting_url_users

    async def has_pending_multi_links(self, uid: int) -> bool:
        """Check if user has pending multi-link confirmation."""
        async with self._state_lock:
            return uid in self._pending_multi_links

    def _normalize_response(self, text: str) -> str:
        return text.strip().lower()

    def _is_affirmative(self, text: str) -> bool:
        """Check if text is an affirmative response."""
        return text in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        """Check if text is a negative response."""
        return text in {"n", "no", "-", "cancel", "stop", "нет", "не"}

    async def _apply_url_security_checks(
        self, message: Any, urls: list[str], uid: int
    ) -> list[str]:
        """Apply shared security checks for URLs from Telegram messages."""
        if not urls:
            return []

        if len(urls) > self.response_formatter.MAX_BATCH_URLS:
            await self.response_formatter.safe_reply(
                message,
                f"❌ Too many URLs ({len(urls)}). Maximum allowed: {self.response_formatter.MAX_BATCH_URLS}.",
            )
            logger.warning(
                "url_batch_limit_exceeded",
                extra={
                    "url_count": len(urls),
                    "max_allowed": self.response_formatter.MAX_BATCH_URLS,
                    "uid": uid,
                },
            )
            return []

        valid_urls = []
        for url in urls:
            is_valid, error_msg = self.response_formatter._validate_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                logger.warning(
                    "invalid_url_submitted", extra={"url": url, "error": error_msg, "uid": uid}
                )

        if not valid_urls:
            await self.response_formatter.safe_reply(
                message, "❌ No valid URLs found after security checks."
            )
        return valid_urls

    async def _request_multi_link_confirmation(
        self,
        message: Any,
        uid: int,
        urls: list[str],
        interaction_id: int,
        start_time: float,
    ) -> None:
        async with self._state_lock:
            self._pending_multi_links[uid] = urls
        # Create inline keyboard buttons for confirmation
        buttons = [
            {"text": "✅ Yes", "callback_data": "multi_confirm_yes"},
            {"text": "❌ No", "callback_data": "multi_confirm_no"},
        ]
        keyboard = self.response_formatter.create_inline_keyboard(buttons)
        await self.response_formatter.safe_reply(
            message, f"Process {len(urls)} links?", reply_markup=keyboard
        )
        logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="confirmation",
                start_time=start_time,
                logger_=logger,
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

        async def process_single_url(
            url: str, progress_tracker: ProgressTracker
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
                    logger.exception(
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

                    logger.exception(
                        "parallel_url_processing_failed",
                        extra={"url": url, "cid": per_link_cid, "error": error_msg, "uid": uid},
                    )

                    # Update progress even on failure
                    await progress_tracker.increment_and_update()

                    return url, False, error_msg

        # Send initial progress message with error handling
        try:
            initial_progress_text = format_progress_message(
                0, len(urls), context="links in parallel", show_bar=False
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

        # Create progress tracker with shared ProgressTracker utility
        async def progress_formatter(
            current: int, total_count: int, msg_id: int | None
        ) -> int | None:
            """Format and send/edit progress updates for URL processing."""
            try:
                # Use shared formatter for consistent progress messages
                progress_text = format_progress_message(
                    current, total_count, context="links in parallel", show_bar=False
                )

                logger.debug(
                    "attempting_progress_update",
                    extra={
                        "completed": current,
                        "total": total_count,
                        "progress_text": progress_text,
                        "progress_msg_id": msg_id,
                        "uid": uid,
                    },
                )

                chat_id = getattr(message.chat, "id", None)
                if chat_id and msg_id:
                    # Try to edit the existing message
                    edit_success = await self.response_formatter.edit_message(
                        chat_id, msg_id, progress_text
                    )

                    if edit_success:
                        logger.debug(
                            "progress_update_sent_successfully",
                            extra={
                                "completed": current,
                                "total": total_count,
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "uid": uid,
                            },
                        )
                        return msg_id

                    logger.warning(
                        "progress_update_edit_failed",
                        extra={
                            "completed": current,
                            "total": total_count,
                            "message_id": msg_id,
                            "uid": uid,
                        },
                    )
                    # Keep returning the same message_id to retry on next update
                    return msg_id

                logger.warning(
                    "progress_update_skipped",
                    extra={
                        "chat_id": chat_id,
                        "progress_msg_id": msg_id,
                        "reason": "missing_chat_id_or_msg_id",
                        "uid": uid,
                    },
                )
                return None
            except Exception as e:
                logger.warning(
                    "progress_update_failed",
                    extra={
                        "error": str(e),
                        "completed": current,
                        "total": total_count,
                        "progress_msg_id": msg_id,
                        "uid": uid,
                    },
                )
                return msg_id

        progress_tracker = ProgressTracker(
            total=len(urls),
            progress_formatter=progress_formatter,
            initial_message_id=progress_msg_id,
            small_batch_threshold=5,  # User-initiated batches use smaller threshold
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
                        logger.exception(
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
                        logger.exception(
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

        # Run batch processing and progress updates concurrently with proper shutdown handling
        progress_task = asyncio.create_task(progress_tracker.process_update_queue())
        try:
            await process_batches()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(
                "parallel_processing_failed",
                extra={"error": str(e), "uid": uid, "url_count": len(urls)},
            )
        finally:
            progress_tracker.mark_complete()
            try:
                await progress_task
            except asyncio.CancelledError:
                raise
            except Exception as progress_exc:
                logger.warning(
                    "progress_update_worker_failed",
                    extra={"error": str(progress_exc), "uid": uid},
                )

        # Send completion summary with detailed feedback using shared formatter
        completion_message = format_completion_message(
            total=len(urls),
            successful=successful,
            failed=failed,
            context="links",
            show_stats=False,  # User-initiated batches are smaller, don't need detailed stats
            failure_rate_threshold=20.0,
        )
        await self.response_formatter.safe_reply(message, completion_message)

        # Safety check: ensure all URLs were processed
        expected_total = len(urls)
        actual_total = successful + failed

        if actual_total != expected_total:
            logger.exception(
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
