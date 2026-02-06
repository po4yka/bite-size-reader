"""URL handling for Telegram bot messages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting import BatchProgressFormatter
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.models.batch_processing import URLBatchStatus
from app.utils.progress_tracker import ProgressTracker

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


# URL processing configuration
URL_MAX_CONCURRENT = 4
URL_MAX_RETRIES = 2  # was 3: fewer retries, each with more time
URL_INITIAL_TIMEOUT_SEC = 90.0  # was 30.0: covers median Firecrawl+LLM+DB
URL_MAX_TIMEOUT_SEC = 180.0
URL_BACKOFF_BASE = 3.0  # was 2.0: longer backoff between retries
URL_BACKOFF_MAX = 60.0


class URLHandler:
    """Handles URL-related message processing and state management."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_processor: URLProcessor,
    ) -> None:
        self.db = db
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self.response_formatter = response_formatter
        self.url_processor = url_processor

        # Lock to protect shared state from concurrent access
        self._state_lock = asyncio.Lock()
        # In-memory state with timestamps for TTL expiry
        self._state_ttl_sec = 120  # 2 minutes
        # uid -> timestamp when added
        self._awaiting_url_users: dict[int, float] = {}
        # uid -> (urls, timestamp)
        self._pending_multi_links: dict[int, tuple[list[str], float]] = {}

    async def add_awaiting_user(self, uid: int) -> None:
        """Add user to awaiting URL list."""
        async with self._state_lock:
            self._awaiting_url_users[uid] = time.time()

    async def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        """Add user to pending multi-links confirmation."""
        async with self._state_lock:
            self._pending_multi_links[uid] = (urls, time.time())

    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        """Cancel any pending URL or multi-link confirmation requests for a user."""
        async with self._state_lock:
            awaiting_cancelled = uid in self._awaiting_url_users
            if awaiting_cancelled:
                self._awaiting_url_users.pop(uid, None)

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
            self._awaiting_url_users.pop(uid, None)

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
            # CRITICAL: Keep lock held during state validation to prevent race conditions
            # This prevents concurrent modifications between retrieval and validation
            async with self._state_lock:
                entry = self._pending_multi_links.get(uid)

                # Unpack timestamped entry
                urls: list[str] | None = None
                if entry is not None:
                    urls = entry[0]

                # Validate state while holding lock (prevents race condition)
                if not urls:
                    logger.warning(
                        "multi_confirm_missing_state", extra={"uid": uid, "cid": correlation_id}
                    )
                    # Release lock before async operations
                else:
                    # Validate URLs while holding lock
                    is_valid = isinstance(urls, list) and all(
                        isinstance(url, str) and url.strip() for url in urls
                    )

                    if not is_valid:
                        logger.warning(
                            "multi_confirm_invalid_state",
                            extra={
                                "uid": uid,
                                "cid": correlation_id,
                                "type": type(urls).__name__,
                                "count": len(urls) if isinstance(urls, list) else None,
                            },
                        )
                        # Drop corrupted state while holding lock
                        self._pending_multi_links.pop(uid, None)
                        urls = None  # Mark as invalid
                    else:
                        # State is valid; remove it before processing to prevent double handling
                        # Pop while still holding lock for atomic operation
                        self._pending_multi_links.pop(uid, None)

            # Now handle results outside lock (async operations)
            if not urls:
                await self.response_formatter.safe_reply(
                    message,
                    "ℹ️ No pending multi-link request to confirm. Please send the links again.",
                )
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.user_repo,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_missing",
                        error_occurred=True,
                        error_message="no_pending_multi_links",
                        start_time=start_time,
                        logger_=logger,
                    )
                return

            # Check if URLs were marked invalid during validation
            if not isinstance(urls, list):
                await self.response_formatter.safe_reply(
                    message,
                    "❌ Pending multi-link request is invalid. Please send the links again.",
                )
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.user_repo,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="confirmation_invalid",
                        error_occurred=True,
                        error_message="invalid_multi_link_cache",
                        start_time=start_time,
                        logger_=logger,
                    )
                return
            await self.response_formatter.safe_reply(
                message, f"🚀 Processing {len(urls)} links in parallel..."
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
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
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="cancelled",
                    start_time=start_time,
                    logger_=logger,
                )

    async def is_awaiting_url(self, uid: int) -> bool:
        """Check if user is awaiting a URL (respects TTL)."""
        async with self._state_lock:
            ts = self._awaiting_url_users.get(uid)
            if ts is None:
                return False
            if time.time() - ts > self._state_ttl_sec:
                self._awaiting_url_users.pop(uid, None)
                return False
            return True

    async def has_pending_multi_links(self, uid: int) -> bool:
        """Check if user has pending multi-link confirmation (respects TTL)."""
        async with self._state_lock:
            entry = self._pending_multi_links.get(uid)
            if entry is None:
                return False
            if time.time() - entry[1] > self._state_ttl_sec:
                self._pending_multi_links.pop(uid, None)
                return False
            return True

    async def cleanup_expired_state(self) -> int:
        """Remove expired awaiting/pending entries. Returns count removed."""
        async with self._state_lock:
            now = time.time()
            cleaned = 0
            expired_awaiting = [
                uid
                for uid, ts in self._awaiting_url_users.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_awaiting:
                del self._awaiting_url_users[uid]
                cleaned += 1
            expired_multi = [
                uid
                for uid, (_, ts) in self._pending_multi_links.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_multi:
                del self._pending_multi_links[uid]
                cleaned += 1
            return cleaned

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
            self._pending_multi_links[uid] = (urls, time.time())
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
                self.user_repo,
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
        """Process multiple URLs in parallel with controlled concurrency and detailed status tracking."""
        if not urls:
            return

        # Initialize batch status tracker
        batch_status = URLBatchStatus.from_urls(urls)

        # Use semaphore to limit concurrent processing (prevent overwhelming external APIs)
        # Adaptive concurrency: 2-4 concurrent based on batch size
        max_concurrent = max(2, min(URL_MAX_CONCURRENT, len(urls)))
        semaphore = asyncio.Semaphore(max_concurrent)

        # Track domains that exhausted all retries on timeout.
        # URLs from these domains are skipped immediately.
        failed_domains: set[str] = set()

        async def process_single_url(
            url: str, progress_tracker: ProgressTracker
        ) -> tuple[str, bool, str, str | None]:
            """Process a single URL with retry and exponential backoff.

            Returns:
                Tuple of (url, success, error_message, title)
            """
            async with semaphore:
                per_link_cid = generate_correlation_id()
                last_error = ""
                error_type = "unknown"
                start_time_ms = time.time() * 1000

                # Resolve domain for fail-fast tracking
                entry = batch_status._find_entry(url)
                url_domain = entry.domain if entry else None

                # Domain fail-fast: skip if another URL from this domain already timed out
                if url_domain and url_domain in failed_domains:
                    processing_time_ms = time.time() * 1000 - start_time_ms
                    batch_status.mark_failed(
                        url,
                        error_type="domain_timeout",
                        error_message=f"Skipped (domain {url_domain} timed out)",
                        processing_time_ms=processing_time_ms,
                    )
                    logger.info(
                        "domain_failfast_skipped",
                        extra={"url": url, "domain": url_domain, "uid": uid},
                    )
                    await progress_tracker.increment_and_update()
                    return url, False, f"Skipped (domain {url_domain} timed out)", None

                # Mark as processing
                batch_status.mark_processing(url)

                async def phase_callback(phase: str) -> None:
                    """Update batch status when URL processing phase changes."""
                    if phase == "extracting":
                        batch_status.mark_extracting(url)
                    elif phase == "analyzing":
                        batch_status.mark_analyzing(url)
                    await progress_tracker.force_update()

                for attempt in range(URL_MAX_RETRIES + 1):
                    # Calculate timeout with exponential increase per retry
                    current_timeout = min(
                        URL_INITIAL_TIMEOUT_SEC * (1.5**attempt),
                        URL_MAX_TIMEOUT_SEC,
                    )

                    logger.debug(
                        "processing_link_parallel",
                        extra={
                            "uid": uid,
                            "url": url,
                            "cid": per_link_cid,
                            "attempt": attempt + 1,
                            "timeout_sec": current_timeout,
                        },
                    )

                    try:
                        # Add timeout protection for individual URL processing
                        result = await asyncio.wait_for(
                            self.url_processor.handle_url_flow(
                                message,
                                url,
                                correlation_id=per_link_cid,
                                batch_mode=True,
                                on_phase_change=phase_callback,
                            ),
                            timeout=current_timeout,
                        )

                        # Calculate processing time
                        processing_time_ms = time.time() * 1000 - start_time_ms

                        # Extract title from result
                        title = None
                        if result and hasattr(result, "title"):
                            title = result.title

                        # Mark as complete with title
                        batch_status.mark_complete(
                            url, title=title, processing_time_ms=processing_time_ms
                        )

                        # Update progress after successful completion
                        await progress_tracker.increment_and_update()

                        return url, True, "", title

                    except TimeoutError:
                        error_type = "timeout"
                        last_error = f"Timeout ({int(current_timeout)}s)"
                        logger.warning(
                            "url_processing_timeout_retry",
                            extra={
                                "url": url,
                                "cid": per_link_cid,
                                "attempt": attempt + 1,
                                "timeout_sec": current_timeout,
                                "uid": uid,
                            },
                        )

                        # Apply backoff before retry
                        if attempt < URL_MAX_RETRIES:
                            backoff = min(URL_BACKOFF_BASE * (2**attempt), URL_BACKOFF_MAX)
                            await asyncio.sleep(backoff)
                            continue

                    except Exception as e:
                        last_error = str(e)
                        transient_keywords = [
                            "timeout",
                            "connection",
                            "network",
                            "rate limit",
                            "503",
                            "502",
                            "429",
                        ]
                        is_transient = any(kw in last_error.lower() for kw in transient_keywords)

                        # Determine error type
                        if "timeout" in last_error.lower():
                            error_type = "timeout"
                        elif "connection" in last_error.lower() or "network" in last_error.lower():
                            error_type = "network"
                        elif "429" in last_error or "rate limit" in last_error.lower():
                            error_type = "rate_limit"
                        else:
                            error_type = "error"

                        if is_transient and attempt < URL_MAX_RETRIES:
                            backoff = min(URL_BACKOFF_BASE * (2**attempt), URL_BACKOFF_MAX)
                            logger.warning(
                                "transient_error_retry",
                                extra={
                                    "url": url,
                                    "cid": per_link_cid,
                                    "attempt": attempt + 1,
                                    "error": last_error,
                                    "backoff_sec": backoff,
                                    "uid": uid,
                                },
                            )
                            await asyncio.sleep(backoff)
                            continue

                        # Non-transient error or max retries exhausted
                        logger.exception(
                            "parallel_url_processing_failed",
                            extra={
                                "url": url,
                                "cid": per_link_cid,
                                "error": last_error,
                                "attempt": attempt + 1,
                                "uid": uid,
                            },
                        )
                        break

                # All retries exhausted - mark as failed
                processing_time_ms = time.time() * 1000 - start_time_ms
                batch_status.mark_failed(
                    url,
                    error_type=error_type,
                    error_message=last_error,
                    processing_time_ms=processing_time_ms,
                )

                # Add domain to fail-fast set on timeout exhaustion
                if error_type == "timeout" and url_domain:
                    failed_domains.add(url_domain)
                    logger.info(
                        "domain_added_to_failfast",
                        extra={"domain": url_domain, "url": url, "uid": uid},
                    )

                logger.error(
                    "url_processing_all_retries_exhausted",
                    extra={
                        "url": url,
                        "cid": per_link_cid,
                        "total_attempts": URL_MAX_RETRIES + 1,
                        "last_error": last_error,
                        "uid": uid,
                    },
                )
                await progress_tracker.increment_and_update()
                return url, False, last_error, None

        # Send initial progress message with error handling
        try:
            initial_progress_text = BatchProgressFormatter.format_progress_message(batch_status)
            progress_msg_id = await self.response_formatter.safe_reply_with_id(
                message, initial_progress_text
            )
            logger.debug(
                "initial_progress_message_created",
                extra={
                    "progress_msg_id": progress_msg_id,
                    "url_count": len(urls),
                    "uid": uid,
                },
            )
        except Exception as e:
            logger.warning(
                "failed_to_create_progress_message",
                extra={"error": str(e), "uid": uid, "url_count": len(urls)},
            )
            progress_msg_id = None

        # Create progress tracker with batch-aware formatter
        async def progress_formatter(
            current: int, total_count: int, msg_id: int | None
        ) -> int | None:
            """Format and send/edit progress updates using batch status."""
            try:
                # Use BatchProgressFormatter for rich progress messages
                progress_text = BatchProgressFormatter.format_progress_message(batch_status)

                logger.debug(
                    "attempting_progress_update",
                    extra={
                        "completed": batch_status.done_count,
                        "total": total_count,
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
                                "completed": batch_status.done_count,
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
                            "completed": batch_status.done_count,
                            "total": total_count,
                            "message_id": msg_id,
                            "uid": uid,
                        },
                    )
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
                        "completed": batch_status.done_count,
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

        # Process URLs in memory-efficient batches to prevent resource exhaustion
        batch_size = min(5, len(urls))

        async def process_batches() -> None:
            """Process URL batches with progress tracking."""
            for batch_start in range(0, len(urls), batch_size):
                batch_end = min(batch_start + batch_size, len(urls))
                batch_urls = urls[batch_start:batch_end]

                # Create tasks for this batch only
                batch_tasks = [process_single_url(url, progress_tracker) for url in batch_urls]

                # Process batch and handle results immediately
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Process results from this batch (status already tracked in process_single_url)
                for result in batch_results:
                    if isinstance(result, Exception):
                        if isinstance(result, asyncio.CancelledError):
                            raise result
                        logger.exception(
                            "unexpected_task_exception", extra={"error": str(result), "uid": uid}
                        )

                # Small delay between batches to prevent overwhelming external APIs
                if batch_end < len(urls):
                    await asyncio.sleep(0.1)

        # Run batch processing and progress updates concurrently
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

        # Send completion summary with detailed batch results
        completion_message = BatchProgressFormatter.format_completion_message(batch_status)
        await self.response_formatter.safe_reply(message, completion_message)

        # Safety check and logging
        expected_total = len(urls)
        actual_total = batch_status.done_count

        if actual_total != expected_total:
            logger.exception(
                "parallel_processing_count_mismatch",
                extra={
                    "uid": uid,
                    "expected_total": expected_total,
                    "actual_total": actual_total,
                    "successful": batch_status.success_count,
                    "failed": batch_status.fail_count,
                },
            )

        logger.info(
            "parallel_processing_complete",
            extra={
                "uid": uid,
                "total": expected_total,
                "successful": batch_status.success_count,
                "failed": batch_status.fail_count,
                "total_time_sec": round(batch_status.total_elapsed_time_sec(), 2),
                "avg_time_ms": round(batch_status.average_processing_time_ms(), 0),
                "count_match": actual_total == expected_total,
            },
        )
