"""Helpers for Telegram message routing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from app.adapters.external.formatting import BatchProgressFormatter
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.user_interactions import async_safe_update_user_interaction
from app.models.batch_processing import URLBatchStatus
from app.security.file_validation import FileValidationError
from app.utils.progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


def is_txt_file_with_urls(message: Any) -> bool:
    """Check if message contains a .txt document that likely contains URLs."""
    if not hasattr(message, "document"):
        return False

    document = getattr(message, "document", None)
    if not document or not hasattr(document, "file_name"):
        return False

    file_name = document.file_name
    return file_name.lower().endswith(".txt")


async def handle_document_file(
    router: Any,
    message: Any,
    correlation_id: str,
    interaction_id: int,
    start_time: float,
) -> None:
    """Handle .txt file processing (files containing URLs)."""
    file_path = None
    try:
        # Download and parse the file
        file_path = await download_file(router, message)
        if not file_path:
            await router.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="Failed to download the uploaded file from Telegram servers.",
            )
            return

        # Parse URLs from the file with security validation
        try:
            urls = parse_txt_file(router, file_path)
        except FileValidationError as exc:
            logger.error(
                "file_validation_failed",
                extra={"error": str(exc), "cid": correlation_id},
            )
            await router.response_formatter.safe_reply(
                message, f"❌ File validation failed: {exc!s}"
            )
            return

        if not urls:
            await router.response_formatter.send_error_notification(
                message,
                "no_urls_found",
                correlation_id,
                details="No valid links starting with http:// or https:// were detected in the file.",
            )
            return

        # Security check: limit batch size
        if len(urls) > router.response_formatter.MAX_BATCH_URLS:
            await router.response_formatter.safe_reply(
                message,
                f"❌ Too many URLs ({len(urls)}). "
                f"Maximum allowed: {router.response_formatter.MAX_BATCH_URLS}.",
            )
            logger.warning(
                "batch_url_limit_exceeded",
                extra={
                    "url_count": len(urls),
                    "max_allowed": router.response_formatter.MAX_BATCH_URLS,
                },
            )
            return

        # Validate each URL for security
        valid_urls = []
        for url in urls:
            is_valid, error_msg = router.response_formatter._validate_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                logger.warning("invalid_url_in_batch", extra={"url": url, "error": error_msg})

        if not valid_urls:
            await router.response_formatter.safe_reply(
                message, "❌ No valid URLs found in the file after security checks."
            )
            return

        # Use only valid URLs
        urls = valid_urls

        # Send initial confirmation message (kept as a standalone message)
        await router.response_formatter.safe_reply(
            message, f"📄 File accepted. Processing {len(urls)} links."
        )
        # Respect formatter rate limits before sending the progress message we'll edit later
        try:
            initial_gap = max(
                0.12,
                (router.response_formatter.MIN_MESSAGE_INTERVAL_MS + 10) / 1000.0,
            )
            await asyncio.sleep(initial_gap)
        except Exception as exc:
            raise_if_cancelled(exc)
        # Create a dedicated progress message that we will edit in-place
        # We use a simple placeholder first, then process_url_batch will update it with BatchProgressFormatter
        progress_message_id = await router.response_formatter.safe_reply_with_id(
            message,
            f"🔄 Preparing to process {len(urls)} links...",
        )
        logger.debug(
            "document_file_processing_started",
            extra={"url_count": len(urls)},
        )

        # Process URLs with optimized parallel processing and detailed status tracking
        uid = message.from_user.id if message.from_user else 0
        await process_url_batch(
            message=message,
            urls=urls,
            uid=uid,
            correlation_id=correlation_id,
            url_processor=router._url_processor,
            response_formatter=router.response_formatter,
            request_repo=router.url_handler.request_repo,
            user_repo=router.user_repo,
            interaction_id=interaction_id,
            start_time=start_time,
            initial_message_id=progress_message_id,
        )

        # Ensure we do not hit rate limiter after the last progress edit
        try:
            min_gap_sec = max(
                0.6,
                (router.response_formatter.MIN_MESSAGE_INTERVAL_MS + 50) / 1000.0,
            )
            await asyncio.sleep(min_gap_sec)
        except Exception as exc:
            raise_if_cancelled(exc)

    except Exception:
        logger.exception("document_file_processing_error", extra={"cid": correlation_id})
        await router.response_formatter.send_error_notification(
            message,
            "unexpected_error",
            correlation_id,
            details="An error occurred while parsing or downloading the uploaded file.",
        )
    finally:
        # Clean up downloaded file with retry logic
        if file_path:
            cleanup_attempts = 0
            max_cleanup_attempts = 3
            cleanup_success = False

            while cleanup_attempts < max_cleanup_attempts and not cleanup_success:
                try:
                    router._file_validator.cleanup_file(file_path)
                    cleanup_success = True
                except PermissionError as exc:
                    cleanup_attempts += 1
                    if cleanup_attempts >= max_cleanup_attempts:
                        logger.error(
                            "file_cleanup_permission_denied",
                            extra={
                                "error": str(exc),
                                "file_path": file_path,
                                "cid": correlation_id,
                                "attempts": cleanup_attempts,
                            },
                        )
                    else:
                        await asyncio.sleep(0.1 * cleanup_attempts)
                except FileNotFoundError:
                    cleanup_success = True
                except Exception as exc:
                    cleanup_attempts += 1
                    logger.error(
                        "file_cleanup_unexpected_error",
                        extra={
                            "error": str(exc),
                            "file_path": file_path,
                            "cid": correlation_id,
                            "error_type": type(exc).__name__,
                            "attempts": cleanup_attempts,
                        },
                    )
                    break


async def download_file(router: Any, message: Any) -> str | None:
    """Download document file to temporary location."""
    try:
        document = getattr(message, "document", None)
        if not document:
            return None

        file_info = await message.download()
        return str(file_info) if file_info else None

    except Exception as exc:
        logger.error("file_download_failed", extra={"error": str(exc)})
        return None


def parse_txt_file(router: Any, file_path: str) -> list[str]:
    """Parse URLs from .txt file with security validation."""
    from app.core.url_utils import normalize_url

    lines = router._file_validator.safe_read_text_file(file_path)

    urls = []
    skipped_count = 0
    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith(("http://", "https://")):
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

            try:
                normalized = normalize_url(line)
                urls.append(normalized)
            except ValueError as exc:
                logger.warning(
                    "invalid_url_in_file",
                    extra={
                        "url_preview": line[:50],
                        "error": str(exc),
                        "line_num": line_num,
                        "file_path": file_path,
                    },
                )
                skipped_count += 1
        elif line.startswith(("http", "www")):
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


async def process_url_batch(
    message: Any,
    urls: list[str],
    uid: int,
    correlation_id: str,
    url_processor: Any,  # URLProcessor
    response_formatter: Any,  # ResponseFormatter
    request_repo: Any,  # SqliteRequestRepositoryAdapter
    user_repo: Any,  # SqliteUserRepositoryAdapter
    interaction_id: int | None = None,
    start_time: float | None = None,
    initial_message_id: int | None = None,
    max_concurrent: int = 4,
    max_retries: int = 2,
    compute_timeout_func: Callable[[str, int], Awaitable[float]] | None = None,
) -> None:
    """Process multiple URLs in parallel with controlled concurrency and detailed status tracking.

    This unified implementation handles both .txt file processing and multi-link text messages.
    """
    if not urls:
        return

    # Initialize batch status tracker
    batch_status = URLBatchStatus.from_urls(urls)

    # Get chat_id from message
    chat_id = getattr(message.chat, "id", None)

    # Pre-register all URLs before processing starts
    # This ensures ALL URLs get database records even if processing fails early
    url_to_request_id: dict[str, int] = {}
    for url in urls:
        try:
            normalized = normalize_url(url)
            dedupe_hash = compute_dedupe_hash(url)
            request_id, is_new = await request_repo.async_create_minimal_request(
                type_="url",
                status="pending",
                correlation_id=generate_correlation_id(),
                chat_id=chat_id,
                user_id=uid,
                input_url=url,
                normalized_url=normalized,
                dedupe_hash=dedupe_hash,
            )
            url_to_request_id[url] = request_id
            logger.debug(
                "pre_registered_batch_url",
                extra={
                    "url": url,
                    "request_id": request_id,
                    "is_new": is_new,
                    "uid": uid,
                },
            )
        except Exception as e:
            # Log but don't fail the whole batch if pre-registration fails
            logger.warning(
                "batch_url_pre_registration_failed",
                extra={"url": url, "error": str(e), "uid": uid},
            )

    # Use semaphore to limit concurrent processing
    semaphore = asyncio.Semaphore(max_concurrent)

    # Track domains that exhausted all retries on timeout
    failed_domains: set[str] = set()
    # Count failures per domain for threshold-based fail-fast
    domain_failure_counts: dict[str, int] = {}
    domain_events: dict[str, asyncio.Event] = {}
    domain_failfast_threshold = 2

    def _get_domain_event(domain: str) -> asyncio.Event:
        if domain not in domain_events:
            domain_events[domain] = asyncio.Event()
        return domain_events[domain]

    async def _update_request_error(
        url: str,
        status: str,
        error_type: str,
        error_message: str,
        processing_time_ms: float,
    ) -> None:
        """Update pre-registered request with error info."""
        request_id = url_to_request_id.get(url)
        if request_id:
            try:
                await request_repo.async_update_request_error(
                    request_id=request_id,
                    status=status,
                    error_type=error_type,
                    error_message=error_message[:500] if error_message else None,
                    processing_time_ms=int(processing_time_ms),
                )
            except Exception as e:
                logger.warning(
                    "failed_to_update_request_error",
                    extra={"url": url, "request_id": request_id, "error": str(e)},
                )

    async def process_single_url(
        url: str, progress_tracker: ProgressTracker
    ) -> tuple[str, bool, str, str | None]:
        """Process a single URL with retry and exponential backoff."""
        async with semaphore:
            per_link_cid = generate_correlation_id()
            last_error = ""
            error_type = "unknown"
            start_time_ms = time.time() * 1000

            # Resolve domain for fail-fast tracking
            entry = batch_status._find_entry(url)
            url_domain = entry.domain if entry else None

            # Domain fail-fast
            if url_domain and url_domain in failed_domains:
                processing_time_ms = time.time() * 1000 - start_time_ms
                skip_error = f"Skipped (domain {url_domain} timed out)"
                batch_status.mark_failed(
                    url,
                    error_type="domain_timeout",
                    error_message=skip_error,
                    processing_time_ms=processing_time_ms,
                )
                await _update_request_error(
                    url, "skipped", "domain_timeout", skip_error, processing_time_ms
                )
                logger.info(
                    "domain_failfast_skipped",
                    extra={"url": url, "domain": url_domain, "uid": uid},
                )
                await progress_tracker.increment_and_update()
                return url, False, skip_error, None

            # Mark as processing
            batch_status.mark_processing(url)

            async def phase_callback(phase: str) -> None:
                """Update batch status when URL processing phase changes."""
                if phase == "extracting":
                    batch_status.mark_extracting(url)
                elif phase == "analyzing":
                    batch_status.mark_analyzing(url)
                elif phase == "retrying":
                    batch_status.mark_retrying(url)
                await progress_tracker.force_update()

            for attempt in range(max_retries + 1):
                if attempt > 0 and url_domain and url_domain in failed_domains:
                    last_error = f"Skipped (domain {url_domain} timed out)"
                    error_type = "domain_timeout"
                    break

                # Calculate timeout
                if compute_timeout_func:
                    current_timeout = await compute_timeout_func(url, attempt)
                else:
                    # Default timeout with backoff
                    current_timeout = min(450.0 * (1.5**attempt), 900.0)

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
                    processing_task = asyncio.create_task(
                        url_processor.handle_url_flow(
                            message,
                            url,
                            correlation_id=per_link_cid,
                            batch_mode=True,
                            on_phase_change=phase_callback,
                        )
                    )

                    tasks_to_race: set[asyncio.Task] = {processing_task}
                    cancel_task: asyncio.Task | None = None
                    if url_domain:
                        cancel_task = asyncio.create_task(_get_domain_event(url_domain).wait())
                        tasks_to_race.add(cancel_task)

                    try:
                        done, pending = await asyncio.wait(
                            tasks_to_race,
                            timeout=current_timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    except asyncio.CancelledError:
                        processing_task.cancel()
                        if cancel_task is not None:
                            cancel_task.cancel()
                        for t in (processing_task, cancel_task):
                            if t is not None:
                                with contextlib.suppress(asyncio.CancelledError, Exception):
                                    await t
                        raise

                    for t in pending:
                        t.cancel()
                    for t in pending:
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await t

                    if not done:
                        raise TimeoutError(
                            f"Timed out after {int(current_timeout)}s (ID: {per_link_cid[:8]})"
                        )

                    if cancel_task is not None and cancel_task in done:
                        last_error = f"Skipped (domain {url_domain} timed out)"
                        error_type = "domain_timeout"
                        break

                    result = processing_task.result()
                    processing_time_ms = time.time() * 1000 - start_time_ms
                    title = None
                    if result and hasattr(result, "title"):
                        title = result.title

                    batch_status.mark_complete(
                        url, title=title, processing_time_ms=processing_time_ms
                    )
                    await progress_tracker.increment_and_update()
                    return url, True, "", title

                except TimeoutError:
                    error_type = "timeout"
                    last_error = f"Timed out after {int(current_timeout)}s (ID: {per_link_cid[:8]})"
                    if attempt < max_retries:
                        backoff = min(3.0 * (2**attempt), 60.0)
                        await asyncio.sleep(backoff)
                        continue

                    if url_domain:
                        domain_failure_counts[url_domain] = (
                            domain_failure_counts.get(url_domain, 0) + 1
                        )
                        if domain_failure_counts[url_domain] >= domain_failfast_threshold:
                            failed_domains.add(url_domain)
                            _get_domain_event(url_domain).set()

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

                    if "timeout" in last_error.lower():
                        error_type = "timeout"
                    elif "connection" in last_error.lower() or "network" in last_error.lower():
                        error_type = "network"
                    elif "429" in last_error or "rate limit" in last_error.lower():
                        error_type = "rate_limit"
                    else:
                        error_type = "error"

                    if is_transient and attempt < max_retries:
                        backoff = min(3.0 * (2**attempt), 60.0)
                        await asyncio.sleep(backoff)
                        continue
                    break

            processing_time_ms = time.time() * 1000 - start_time_ms
            batch_status.mark_failed(
                url,
                error_type=error_type,
                error_message=last_error,
                processing_time_ms=processing_time_ms,
            )
            await _update_request_error(url, "error", error_type, last_error, processing_time_ms)
            await progress_tracker.increment_and_update()
            return url, False, last_error, None

    # Create progress tracker with batch-aware formatter
    async def progress_formatter(current: int, total_count: int, msg_id: int | None) -> int | None:
        try:
            progress_text = BatchProgressFormatter.format_progress_message(batch_status)
            chat_id = getattr(message.chat, "id", None)
            if chat_id and msg_id:
                edit_success = await response_formatter.edit_message(
                    chat_id, msg_id, progress_text, parse_mode="HTML"
                )
                if edit_success:
                    return msg_id
            return msg_id
        except Exception:
            return msg_id

    # If initial_message_id is not provided, send the initial message
    if initial_message_id is None:
        try:
            initial_text = BatchProgressFormatter.format_progress_message(batch_status)
            initial_message_id = await response_formatter.safe_reply_with_id(
                message, initial_text, parse_mode="HTML"
            )
        except Exception:
            initial_message_id = None

    progress_tracker = ProgressTracker(
        total=len(urls),
        progress_formatter=progress_formatter,
        initial_message_id=initial_message_id,
        small_batch_threshold=5,
    )

    progress_task = asyncio.create_task(progress_tracker.process_update_queue())

    async def heartbeat() -> None:
        """Force periodic UI updates to show live elapsed time."""
        while not progress_tracker.is_complete:
            try:
                await asyncio.sleep(5)
                await progress_tracker.force_update()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("progress_heartbeat_failed", exc_info=True)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        batch_size = min(5, len(urls))
        for batch_start in range(0, len(urls), batch_size):
            batch_end = min(batch_start + batch_size, len(urls))
            batch_urls = urls[batch_start:batch_end]
            batch_tasks = [process_single_url(url, progress_tracker) for url in batch_urls]
            await asyncio.gather(*batch_tasks, return_exceptions=True)
            if batch_end < len(urls):
                await asyncio.sleep(0.1)
    finally:
        heartbeat_task.cancel()
        progress_tracker.mark_complete()
        await progress_task

    # Send completion message
    completion_message = BatchProgressFormatter.format_completion_message(batch_status)
    await response_formatter.safe_reply(message, completion_message, parse_mode="HTML")

    if interaction_id and start_time:
        await async_safe_update_user_interaction(
            user_repo,
            interaction_id=interaction_id,
            response_sent=True,
            response_type="batch_complete",
            start_time=start_time,
            logger_=logger,
        )


def should_notify_rate_limit(router: Any, uid: int) -> bool:
    """Determine if we should notify a user about rate limiting."""
    now = time.time()
    deadline = router._rate_limit_notified_until.get(uid, 0.0)
    if now >= deadline:
        router._rate_limit_notified_until[uid] = now + router._rate_limit_notice_window
        return True
    logger.debug(
        "rate_limit_notice_suppressed",
        extra={
            "uid": uid,
            "remaining_suppression": max(0.0, deadline - now),
        },
    )
    return False


def is_duplicate_message(
    router: Any,
    message_key: tuple[int, int, int],
    text_signature: str,
) -> bool:
    """Return True if we've processed this message recently."""
    now = time.time()
    last_seen = router._recent_message_ids.get(message_key)
    if (
        last_seen is not None
        and now - last_seen[0] < router._recent_message_ttl
        and last_seen[1] == text_signature
    ):
        return True
    router._recent_message_ids[message_key] = (now, text_signature)
    if len(router._recent_message_ids) > 2000:
        cutoff = now - router._recent_message_ttl
        router._recent_message_ids = {
            key: (ts, signature)
            for key, (ts, signature) in router._recent_message_ids.items()
            if ts >= cutoff
        }
    return False
