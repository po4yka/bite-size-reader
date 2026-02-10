"""Helpers for Telegram message routing."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.config.integrations import BatchAnalysisConfig

from app.adapters.external.formatting import BatchProgressFormatter
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.user_interactions import async_safe_update_user_interaction
from app.models.batch_processing import URLBatchStatus, URLStatus
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
) -> BatchContext | None:
    """Process multiple URLs in parallel with controlled concurrency and detailed status tracking.

    This unified implementation handles both .txt file processing and multi-link text messages.

    Returns:
        BatchContext with batch processing results, or None if no URLs provided.
    """
    if not urls:
        return None

    # Pre-register all URLs before processing starts
    # This ensures ALL URLs get database records even if processing fails early
    url_to_request_id: dict[str, int] = {}
    urls_to_process: list[str] = []

    # Get chat_id from message
    chat_id = getattr(message.chat, "id", None)

    # Initialize batch status tracker
    batch_status = URLBatchStatus.from_urls(urls)

    for url in urls:
        try:
            normalized = normalize_url(url)
            dedupe_hash = compute_dedupe_hash(url)

            # Check if we already have a successful summary for this URL
            existing_request = await request_repo.async_get_request_by_dedupe_hash(dedupe_hash)
            if existing_request and existing_request.get("status") == "ok":
                req_id = existing_request.get("id")
                # Double check summary table
                summary = await url_processor.summary_repo.async_get_summary_by_request(req_id)
                if summary:
                    # Extract title from cached summary
                    payload = summary.get("json_payload")
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except Exception:
                            payload = {}

                    from app.adapters.content.url_processor import URLProcessingFlowResult

                    title = URLProcessingFlowResult.from_summary(payload).title

                    batch_status.mark_cached(url, title=title)
                    logger.debug(
                        "batch_url_cache_hit",
                        extra={"url": url, "request_id": req_id, "uid": uid},
                    )
                    # Audit the cache hit so it's visible in logs
                    if hasattr(url_processor, "_audit"):
                        url_processor._audit(
                            "INFO",
                            "batch_url_cache_hit",
                            {"url": url, "request_id": req_id, "uid": uid},
                        )
                    continue

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
            urls_to_process.append(url)
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
            urls_to_process.append(url)

    # Use semaphore to limit concurrent processing
    semaphore = asyncio.Semaphore(max_concurrent)

    # Add a small delay to ensure the initial message is sent and visible
    # This prevents race conditions where we try to edit/reply too quickly
    await asyncio.sleep(0.5)

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
        # If already marked as cached during pre-registration, skip processing
        entry = batch_status._find_entry(url)
        if entry and entry.status == URLStatus.CACHED:
            # Add a small delay for cached items to allow UI updates to flow and avoid rate limits
            # 0.5s * 4 links = ~2s, which is a safe interval for Telegram edits
            await asyncio.sleep(0.5)
            await progress_tracker.increment_and_update()
            return url, True, "", entry.title

        async with semaphore:
            per_link_cid = generate_correlation_id()
            last_error = ""
            error_type = "unknown"
            start_time_ms = time.time() * 1000

            # Resolve domain for fail-fast tracking
            if entry is None:
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

            async def phase_callback(
                phase: str,
                title: str | None = None,
                content_length: int | None = None,
                model: str | None = None,
            ) -> None:
                """Update batch status when URL processing phase changes."""
                if phase == "extracting":
                    batch_status.mark_extracting(url)
                elif phase == "analyzing":
                    batch_status.mark_analyzing(
                        url, title=title, content_length=content_length, model=model
                    )
                elif phase == "retrying":
                    batch_status.mark_retrying(url)
                elif phase == "waiting":
                    batch_status.mark_retry_waiting(url)
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
                        batch_status.mark_retry_waiting(url)
                        await progress_tracker.force_update()
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
        update_interval=1.0,
        small_batch_threshold=0,
        progress_threshold_percentage=25.0,
    )

    progress_task = asyncio.create_task(progress_tracker.process_update_queue())

    async def heartbeat() -> None:
        """Force periodic UI updates to show live elapsed time."""
        while not progress_tracker.is_complete:
            try:
                await asyncio.sleep(3)
                await progress_tracker.force_update()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("progress_heartbeat_failed", exc_info=True)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        # Create tasks for ALL URLs (including cached ones for consistent status reporting)
        all_tasks = [process_single_url(url, progress_tracker) for url in urls]
        await asyncio.gather(*all_tasks, return_exceptions=True)
    finally:
        heartbeat_task.cancel()
        progress_tracker.mark_complete()
        try:
            # Allow more time for final progress updates to sync, especially if rate limited
            await asyncio.wait_for(progress_task, timeout=10.0)
        except Exception:
            progress_task.cancel()

    # Small delay to avoid hitting Telegram's per-chat rate limit (30 messages/sec)
    # when switching from frequent edits to the final summary reply.
    await asyncio.sleep(0.8)

    # Send completion message
    completion_message = BatchProgressFormatter.format_completion_message(batch_status)
    logger.info(
        "sending_batch_completion",
        extra={"uid": uid, "total": len(urls), "success": batch_status.success_count},
    )
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

    # Return batch context for relationship analysis
    return BatchContext(
        batch_status=batch_status,
        url_to_request_id=url_to_request_id,
        correlation_id=correlation_id,
        uid=uid,
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


class BatchContext:
    """Context object returned from batch processing for relationship analysis."""

    def __init__(
        self,
        batch_status: URLBatchStatus,
        url_to_request_id: dict[str, int],
        correlation_id: str,
        uid: int,
    ):
        self.batch_status = batch_status
        self.url_to_request_id = url_to_request_id
        self.correlation_id = correlation_id
        self.uid = uid


async def run_batch_relationship_analysis(
    batch_context: BatchContext,
    message: Any,
    response_formatter: Any,
    summary_repo: Any,
    batch_session_repo: Any,
    llm_client: Any,
    batch_config: BatchAnalysisConfig,
) -> None:
    """Run relationship analysis on a completed batch of articles.

    This function:
    1. Creates a BatchSession record
    2. Fetches all successful summaries
    3. Runs RelationshipAnalysisAgent
    4. If relationship found, runs CombinedSummaryAgent
    5. Persists results and sends combined analysis to user

    Args:
        batch_context: Context from batch processing
        message: Telegram message for replies
        response_formatter: ResponseFormatter instance
        summary_repo: Summary repository
        batch_session_repo: BatchSession repository
        llm_client: LLM client for agents
        batch_config: Batch analysis configuration
    """
    from app.agents.combined_summary_agent import CombinedSummaryAgent
    from app.agents.relationship_analysis_agent import RelationshipAnalysisAgent
    from app.models.batch_analysis import (
        ArticleMetadata,
        CombinedSummaryInput,
        RelationshipAnalysisInput,
        RelationshipType,
    )

    batch_status = batch_context.batch_status
    url_to_request_id = batch_context.url_to_request_id
    correlation_id = batch_context.correlation_id
    uid = batch_context.uid

    # Check if we have enough successful articles
    if batch_status.success_count < batch_config.min_articles:
        logger.debug(
            "batch_analysis_skipped_insufficient_articles",
            extra={
                "success_count": batch_status.success_count,
                "min_required": batch_config.min_articles,
                "cid": correlation_id,
            },
        )
        return

    start_time_ms = time.time() * 1000

    try:
        # Create batch session record
        session_id = await batch_session_repo.async_create_batch_session(
            user_id=uid,
            correlation_id=correlation_id,
            total_urls=batch_status.total,
        )

        # Get successful request IDs
        successful_request_ids = []
        for url, request_id in url_to_request_id.items():
            entry = batch_status._find_entry(url)
            if entry and entry.status in (URLStatus.COMPLETE, URLStatus.CACHED):
                successful_request_ids.append(request_id)

        if len(successful_request_ids) < batch_config.min_articles:
            await batch_session_repo.async_update_batch_session_status(
                session_id, "completed", analysis_status="skipped"
            )
            return

        # Fetch summaries for successful requests
        summaries = await summary_repo.async_get_summaries_by_request_ids(successful_request_ids)

        # Build article metadata for analysis
        articles: list[ArticleMetadata] = []
        full_summaries: list[dict[str, Any]] = []

        for i, request_id in enumerate(successful_request_ids):
            summary_data = summaries.get(request_id)
            if not summary_data:
                continue

            # Add batch session item
            await batch_session_repo.async_add_batch_session_item(
                session_id=session_id,
                request_id=request_id,
                position=i,
            )

            payload = summary_data.get("json_payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}

            # Find the URL for this request_id
            url = next((u for u, rid in url_to_request_id.items() if rid == request_id), "")

            # Extract domain from URL
            domain = None
            if url:
                try:
                    domain = urlparse(url).netloc
                except Exception:
                    pass

            # Extract entities as strings
            entities = []
            raw_entities = payload.get("entities", [])
            if isinstance(raw_entities, list):
                for e in raw_entities:
                    if isinstance(e, dict) and "name" in e:
                        entities.append(e["name"])
                    elif isinstance(e, str):
                        entities.append(e)

            articles.append(
                ArticleMetadata(
                    request_id=request_id,
                    url=url,
                    title=payload.get("title"),
                    author=payload.get("author"),
                    domain=domain,
                    published_at=payload.get("published_at"),
                    topic_tags=payload.get("topic_tags", []),
                    entities=entities,
                    summary_250=payload.get("summary_250"),
                    summary_1000=payload.get("summary_1000"),
                    language=summary_data.get("lang"),
                )
            )
            full_summaries.append(payload)

        if len(articles) < batch_config.min_articles:
            await batch_session_repo.async_update_batch_session_status(
                session_id, "completed", analysis_status="skipped"
            )
            return

        # Update session counts
        await batch_session_repo.async_update_batch_session_counts(
            session_id,
            successful_count=batch_status.success_count,
            failed_count=batch_status.fail_count,
        )

        # Determine language from articles
        languages = [a.language for a in articles if a.language]
        language = languages[0] if languages else "en"

        # Run relationship analysis
        await batch_session_repo.async_update_batch_session_status(
            session_id, "processing", analysis_status="analyzing"
        )

        relationship_agent = RelationshipAnalysisAgent(
            llm_client=llm_client if batch_config.use_llm_for_analysis else None,
            correlation_id=correlation_id,
        )

        analysis_input = RelationshipAnalysisInput(
            articles=articles,
            correlation_id=correlation_id,
            language=language,
            series_threshold=batch_config.series_threshold,
            cluster_threshold=batch_config.cluster_threshold,
        )

        analysis_result = await relationship_agent.execute(analysis_input)

        if not analysis_result.success or not analysis_result.output:
            logger.warning(
                "batch_relationship_analysis_failed",
                extra={"error": analysis_result.error, "cid": correlation_id},
            )
            await batch_session_repo.async_update_batch_session_status(
                session_id, "completed", analysis_status="error"
            )
            return

        relationship = analysis_result.output

        # Persist relationship results
        relationship_metadata = {
            "series_info": relationship.series_info.model_dump()
            if relationship.series_info
            else None,
            "cluster_info": relationship.cluster_info.model_dump()
            if relationship.cluster_info
            else None,
            "reasoning": relationship.reasoning,
            "signals_used": relationship.signals_used,
        }

        await batch_session_repo.async_update_batch_session_relationship(
            session_id,
            relationship_type=relationship.relationship_type.value,
            relationship_confidence=relationship.confidence,
            relationship_metadata=relationship_metadata,
        )

        # If unrelated, we're done
        if relationship.relationship_type == RelationshipType.UNRELATED:
            processing_time_ms = int(time.time() * 1000 - start_time_ms)
            await batch_session_repo.async_update_batch_session_status(
                session_id, "completed", processing_time_ms=processing_time_ms
            )
            logger.info(
                "batch_analysis_complete_unrelated",
                extra={"session_id": session_id, "cid": correlation_id},
            )
            return

        # Update series info for items if detected
        if relationship.series_info and relationship.series_info.article_order:
            for i, req_id in enumerate(relationship.series_info.article_order, 1):
                # Find the item and update it
                items = await batch_session_repo.async_get_batch_session_items(session_id)
                for item in items:
                    if item.get("request") == req_id:
                        await batch_session_repo.async_update_batch_session_item_series_info(
                            item["id"],
                            is_series_part=True,
                            series_order=i,
                            series_title=relationship.series_info.series_title,
                        )
                        break

        # Generate combined summary if enabled
        combined_summary = None
        if batch_config.combined_summary_enabled and llm_client:
            combined_agent = CombinedSummaryAgent(
                llm_client=llm_client,
                correlation_id=correlation_id,
            )

            combined_input = CombinedSummaryInput(
                articles=articles,
                relationship=relationship,
                full_summaries=full_summaries,
                correlation_id=correlation_id,
                language=language,
            )

            combined_result = await combined_agent.execute(combined_input)

            if combined_result.success and combined_result.output:
                combined_summary = combined_result.output
                await batch_session_repo.async_update_batch_session_combined_summary(
                    session_id, combined_summary.model_dump()
                )

        processing_time_ms = int(time.time() * 1000 - start_time_ms)
        await batch_session_repo.async_update_batch_session_status(
            session_id, "completed", processing_time_ms=processing_time_ms
        )

        # Send relationship analysis result to user
        await _send_batch_analysis_result(
            message,
            response_formatter,
            relationship,
            combined_summary,
            articles,
            language,
        )

        logger.info(
            "batch_analysis_complete",
            extra={
                "session_id": session_id,
                "relationship_type": relationship.relationship_type.value,
                "confidence": relationship.confidence,
                "combined_summary": combined_summary is not None,
                "processing_time_ms": processing_time_ms,
                "cid": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            "batch_relationship_analysis_error",
            extra={"error": str(e), "cid": correlation_id},
        )


async def _send_batch_analysis_result(
    message: Any,
    response_formatter: Any,
    relationship: Any,  # RelationshipAnalysisOutput
    combined_summary: Any,  # CombinedSummaryOutput | None
    articles: list[Any],
    language: str,
) -> None:
    """Send batch analysis results to the user."""
    from app.models.batch_analysis import RelationshipType

    # Build relationship type display
    type_labels = {
        RelationshipType.SERIES: ("Series Detected", "Обнаружена серия"),
        RelationshipType.TOPIC_CLUSTER: ("Topic Cluster", "Тематический кластер"),
        RelationshipType.AUTHOR_COLLECTION: ("Author Collection", "Коллекция автора"),
        RelationshipType.DOMAIN_RELATED: ("Related Content", "Связанный контент"),
    }

    type_label = type_labels.get(relationship.relationship_type, ("Related", "Связано"))
    label = type_label[1] if language == "ru" else type_label[0]

    # Build message
    parts = []
    parts.append(f"<b>{label}</b> ({relationship.confidence:.0%} confidence)")

    if relationship.reasoning:
        parts.append(f"\n{relationship.reasoning}")

    # Series info
    if relationship.series_info:
        si = relationship.series_info
        if si.series_title:
            parts.append(f"\n<b>Series:</b> {si.series_title}")
        if si.numbering_pattern:
            parts.append(f"<b>Pattern:</b> {si.numbering_pattern}")

    # Cluster info
    if relationship.cluster_info:
        ci = relationship.cluster_info
        if ci.cluster_topic:
            parts.append(f"\n<b>Topic:</b> {ci.cluster_topic}")
        if ci.shared_entities:
            parts.append(f"<b>Shared entities:</b> {', '.join(ci.shared_entities[:5])}")
        if ci.shared_tags:
            parts.append(f"<b>Shared tags:</b> {', '.join(ci.shared_tags[:5])}")

    # Combined summary
    if combined_summary:
        parts.append("\n---")
        parts.append(f"\n<b>Thematic Arc:</b>\n{combined_summary.thematic_arc}")

        if combined_summary.synthesized_insights:
            insights_header = (
                "Synthesized Insights" if language != "ru" else "Синтезированные инсайты"
            )
            parts.append(f"\n<b>{insights_header}:</b>")
            for insight in combined_summary.synthesized_insights[:5]:
                parts.append(f"- {insight}")

        if combined_summary.contradictions:
            contradictions_header = "Contradictions" if language != "ru" else "Противоречия"
            parts.append(f"\n<b>{contradictions_header}:</b>")
            for contradiction in combined_summary.contradictions[:3]:
                parts.append(f"- {contradiction}")

        if combined_summary.reading_order_rationale:
            order_header = "Reading Order" if language != "ru" else "Порядок чтения"
            parts.append(f"\n<b>{order_header}:</b> {combined_summary.reading_order_rationale}")

        if combined_summary.total_reading_time_min:
            time_header = "Total Reading Time" if language != "ru" else "Общее время чтения"
            parts.append(f"\n<b>{time_header}:</b> {combined_summary.total_reading_time_min} min")

    text = "\n".join(parts)
    await response_formatter.safe_reply(message, text, parse_mode="HTML")
