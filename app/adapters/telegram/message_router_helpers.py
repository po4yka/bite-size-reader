"""Helpers for Telegram message routing."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import generate_correlation_id
from app.db.user_interactions import async_safe_update_user_interaction
from app.security.file_validation import FileValidationError
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.message_formatter import create_progress_bar, format_progress_message
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
            await router.response_formatter.safe_reply(message, "Failed to download the file.")
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
            await router.response_formatter.safe_reply(message, "No valid URLs found in the file.")
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
        progress_message_id = await router.response_formatter.safe_reply_with_id(
            message,
            f"🔄 Processing links: 0/{len(urls)}\n{create_progress_bar(0, len(urls))}",
        )
        logger.debug(
            "document_file_processing_started",
            extra={"url_count": len(urls)},
        )

        # Process URLs with optimized parallel processing and memory management
        await process_urls_sequentially(
            router,
            message,
            urls,
            correlation_id,
            interaction_id,
            start_time,
            progress_message_id,
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
        await router.response_formatter.safe_reply(
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


async def process_urls_sequentially(
    router: Any,
    message: Any,
    urls: list[str],
    correlation_id: str,
    interaction_id: int,
    start_time: float,
    progress_message_id: int | None = None,
) -> None:
    """Process URLs with optimized parallel processing and batch progress updates."""
    total = len(urls)
    semaphore = asyncio.Semaphore(min(5, total))

    failure_threshold = min(10, max(3, total // 3))
    circuit_breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        timeout=60.0,
        success_threshold=3,
    )

    async def process_single_url(
        url: str, progress_tracker: ProgressTracker, max_retries: int = 3
    ) -> tuple[str, bool, str]:
        """Process a single URL with retry logic and return (url, success, error_message)."""

        async with semaphore:
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
                for attempt in range(1, max_retries + 1):
                    try:
                        result = await asyncio.wait_for(
                            process_url_silently(
                                router, message, url, per_link_cid, interaction_id
                            ),
                            timeout=600,
                        )

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
                            circuit_breaker.record_success()
                            return (url, True, "")

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
                            circuit_breaker.record_failure()
                            error_msg = result.error_message or "URL processing failed"
                            return (url, False, error_msg)

                        wait_time = 2 ** (attempt - 1)
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

                    except TimeoutError:
                        error_msg = f"Timeout after 10 minutes (attempt {attempt}/{max_retries})"
                        logger.error(
                            "url_processing_timeout",
                            extra={"url": url, "cid": per_link_cid, "attempt": attempt},
                        )

                        if attempt < max_retries:
                            wait_time = 2 ** (attempt - 1)
                            logger.info(
                                "retrying_after_timeout",
                                extra={"url": url, "wait_time": wait_time},
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        circuit_breaker.record_failure()
                        return (url, False, error_msg)

                    except Exception as exc:
                        error_msg = f"{type(exc).__name__}: {exc!s}"
                        logger.error(
                            "url_processing_exception",
                            extra={
                                "url": url,
                                "cid": per_link_cid,
                                "attempt": attempt,
                                "error_type": type(exc).__name__,
                            },
                        )

                        circuit_breaker.record_failure()
                        return (url, False, error_msg)

                error_msg = f"Processing failed after {max_retries} attempts"
                circuit_breaker.record_failure()
                return (url, False, error_msg)

            except asyncio.CancelledError:
                raise

            finally:
                if final_result is not None:
                    await progress_tracker.increment_and_update()

    async def progress_formatter(current: int, total_count: int, msg_id: int | None) -> int | None:
        return await send_progress_update(router, message, current, total_count, msg_id)

    progress_tracker = ProgressTracker(
        total=total,
        progress_formatter=progress_formatter,
        initial_message_id=progress_message_id,
        small_batch_threshold=10,
    )

    batch_size = min(5, total)

    async def process_batches():
        """Process URL batches with progress tracking."""
        from app.models.batch_processing import FailedURLDetail

        batch_successful = 0
        batch_failed = 0
        batch_failed_urls: list[FailedURLDetail] = []

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch_urls = urls[batch_start:batch_end]

            batch_tasks = [process_single_url(url, progress_tracker) for url in batch_urls]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                logger.debug(
                    "batch_result_debug",
                    extra={
                        "result_type": type(result).__name__,
                        "result_value": (
                            str(result)[:200] if not isinstance(result, Exception) else str(result)
                        ),
                        "is_tuple": isinstance(result, tuple),
                        "tuple_len": len(result) if isinstance(result, tuple) else 0,
                        "cid": correlation_id,
                    },
                )

                if isinstance(result, Exception):
                    if isinstance(result, asyncio.CancelledError):
                        raise result
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
                        error_type = "unknown"
                        retry_recommended = False
                        if "timeout" in error_msg.lower():
                            error_type = "timeout"
                            retry_recommended = True
                        elif "circuit breaker" in error_msg.lower():
                            error_type = "circuit_breaker"
                            retry_recommended = True
                        elif "network" in error_msg.lower():
                            error_type = "network"
                            retry_recommended = True
                        elif "validation" in error_msg.lower():
                            error_type = "validation"
                            retry_recommended = False
                        elif "service_unavailable" in error_msg.lower():
                            error_type = "service_unavailable"
                            retry_recommended = True

                        batch_failed_urls.append(
                            FailedURLDetail(
                                url=url,
                                error_type=error_type,
                                error_message=error_msg,
                                retry_recommended=retry_recommended,
                                attempts=1,
                            )
                        )

            if batch_start + batch_size < total:
                delay = 0.3 if total > 10 else 0.2
                await asyncio.sleep(delay)

        return batch_successful, batch_failed, batch_failed_urls

    if total == 0:
        return

    max_batch_time = max(600, total * 60)
    try:
        successful, failed, failed_urls = await asyncio.wait_for(
            process_batches(), timeout=max_batch_time
        )
    except TimeoutError:
        logger.error("batch_processing_timeout", extra={"total": total, "cid": correlation_id})
        await router.response_formatter.safe_reply(
            message,
            f"❌ Batch processing timed out after {max_batch_time // 60} minutes. "
            "Some URLs may not have been processed.",
        )
        return

    completed = successful + failed

    if completed < total:
        logger.warning(
            "batch_processing_incomplete",
            extra={
                "expected_total": total,
                "actual_completed": completed,
                "successful": successful,
                "failed": failed,
                "cid": correlation_id,
            },
        )
        await router.response_formatter.safe_reply(
            message,
            f"⚠️ Processing incomplete: {completed}/{total} URLs processed. "
            f"{total - completed} URLs may have been skipped.",
        )

    if failed_urls:
        from app.models.batch_processing import FailedURLDetail

        failed_summary = ", ".join([f.url for f in failed_urls[:5]])
        if len(failed_urls) > 5:
            failed_summary += f" and {len(failed_urls) - 5} more"

        failed_detail = "\n".join(
            [
                f"• {f.url} ({f.error_type})"
                for f in failed_urls[:5]
                if isinstance(f, FailedURLDetail)
            ]
        )
        if len(failed_urls) > 5:
            failed_detail += f"\n... and {len(failed_urls) - 5} more"

        await router.response_formatter.safe_reply(
            message,
            "❌ Some URLs failed to process:\n"
            f"{failed_detail}\n\n"
            "You can retry these URLs individually.",
        )

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
        await router.response_formatter.safe_reply(
            message,
            f"⚠️ Processing completed with count mismatch. Expected {total}, processed {completed}.",
        )

    logger.info(
        "batch_processing_complete",
        extra={
            "total": total,
            "completed": completed,
            "successful": successful,
            "failed": len(failed_urls),
            "failed_urls": failed_urls[:5],
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "count_match": completed == total,
        },
    )

    if interaction_id:
        await async_safe_update_user_interaction(
            router.user_repo,
            interaction_id=interaction_id,
            response_sent=True,
            response_type="batch_processing_complete",
            start_time=start_time,
            logger_=logger,
        )


async def process_url_silently(
    router: Any,
    message: Any,
    url: str,
    correlation_id: str,
    interaction_id: int,
):
    """Process a single URL without sending Telegram responses."""
    import time as _time

    from app.models.batch_processing import URLProcessingResult

    start_time = _time.time()

    try:
        await router._url_processor.handle_url_flow(
            message,
            url,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=True,
        )
        processing_time = (_time.time() - start_time) * 1000
        return URLProcessingResult.success_result(url, processing_time_ms=processing_time)

    except TimeoutError as exc:
        raise_if_cancelled(exc)
        logger.error(
            "url_processing_timeout",
            extra={"url": url, "cid": correlation_id, "error": str(exc)},
        )
        return URLProcessingResult.timeout_result(url, timeout_sec=600)

    except (httpx.NetworkError, httpx.ConnectError, httpx.TimeoutException) as exc:
        raise_if_cancelled(exc)
        logger.error(
            "url_processing_network_error",
            extra={"url": url, "cid": correlation_id, "error": str(exc)},
        )
        return URLProcessingResult.network_error_result(url, exc)

    except ValueError as exc:
        raise_if_cancelled(exc)
        logger.error(
            "url_processing_validation_error",
            extra={"url": url, "cid": correlation_id, "error": str(exc)},
        )
        return URLProcessingResult.validation_error_result(url, exc)

    except Exception as exc:
        raise_if_cancelled(exc)
        logger.error(
            "url_processing_failed",
            extra={
                "url": url,
                "cid": correlation_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return URLProcessingResult.generic_error_result(url, exc)


async def send_progress_update(
    router: Any,
    message: Any,
    current: int,
    total: int,
    message_id: int | None = None,
) -> int | None:
    """Send or edit the Telegram progress message."""
    progress_text = format_progress_message(current, total, context="links", show_bar=True)

    chat_id = getattr(message.chat, "id", None)

    if message_id is not None and chat_id is not None:
        edit_success = await router.response_formatter.edit_message(
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
        logger.warning(
            "progress_update_edit_failed",
            extra={
                "current": current,
                "total": total,
                "message_id": message_id,
                "fallback": "will_send_new_message",
            },
        )
    elif message_id is not None:
        logger.warning(
            "progress_update_no_chat_id",
            extra={"message_id": message_id, "current": current, "total": total},
        )

    try:
        new_message_id = await router.response_formatter.safe_reply_with_id(message, progress_text)
    except Exception as send_error:
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
