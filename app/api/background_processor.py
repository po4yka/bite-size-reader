"""Background request processor for Mobile API.

This module provides async request processing without requiring Celery/Redis.
It integrates with the existing Telegram bot processing pipeline.

Note: This module uses legacy configuration patterns and needs refactoring
to match the current AppConfig structure (cfg.firecrawl, cfg.openrouter, cfg.runtime
instead of cfg.credentials and cfg.llm). Type checking temporarily disabled.
"""

# mypy: ignore-errors
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.db.database import Database
from app.db.models import Request as RequestModel, Summary

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


# Global instances (initialized once)
_processor_instances: dict[str, Any] = {}
_semaphore: asyncio.Semaphore | None = None
_cfg: AppConfig | None = None
_request_locks: dict[int, asyncio.Lock] = {}


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the global semaphore for rate limiting."""
    global _semaphore
    limit = 4
    if _cfg:
        limit = max(1, min(100, _cfg.runtime.max_concurrent_calls))
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(limit)
    return _semaphore


def _get_request_lock(request_id: int) -> asyncio.Lock:
    """Get per-request lock to ensure idempotent processing."""
    if request_id not in _request_locks:
        _request_locks[request_id] = asyncio.Lock()
    return _request_locks[request_id]


def _audit_func(level: str, event: str, details: dict) -> None:
    """Simple audit function for logging."""
    logger.log(
        logging.INFO if level == "info" else logging.ERROR,
        event,
        extra=details,
    )


async def _run_with_retries(
    func: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Execute coroutine with simple exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:  # pragma: no cover - best effort logging
            last_error = exc
            delay = base_delay * attempt
            logger.warning(
                "processor_retry", extra={"attempt": attempt, "delay": delay, "error": str(exc)}
            )
            await asyncio.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("Retry loop exited without result or error")


async def _get_url_processor() -> URLProcessor:
    """Get or create the URL processor singleton."""
    if "url_processor" in _processor_instances:
        return _processor_instances["url_processor"]

    # Initialize components
    global _cfg
    cfg = load_config()
    _cfg = cfg

    db = Database(
        path=cfg.runtime.db_path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )

    firecrawl = FirecrawlClient(
        api_key=cfg.firecrawl.api_key,
        timeout=cfg.runtime.request_timeout_sec,
        max_connections=cfg.firecrawl.max_connections,
        max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
        keepalive_expiry=cfg.firecrawl.keepalive_expiry,
    )

    openrouter = OpenRouterClient(
        api_key=cfg.openrouter.api_key,
        model=cfg.openrouter.model,
        fallback_models=list(cfg.openrouter.fallback_models),
        http_referer=cfg.openrouter.http_referer,
        x_title=cfg.openrouter.x_title,
        timeout_sec=cfg.runtime.request_timeout_sec,
        debug_payloads=cfg.runtime.debug_payloads,
        provider_order=list(cfg.openrouter.provider_order),
        enable_stats=cfg.openrouter.enable_stats,
        enable_structured_outputs=cfg.openrouter.enable_structured_outputs,
        structured_output_mode=cfg.openrouter.structured_output_mode,
        require_parameters=cfg.openrouter.require_parameters,
        auto_fallback_structured=cfg.openrouter.auto_fallback_structured,
        max_response_size_mb=cfg.openrouter.max_response_size_mb,
    )

    response_formatter = ResponseFormatter(telegram_limits=cfg.telegram_limits)

    # Create URL processor
    url_processor = URLProcessor(
        cfg=cfg,
        db=db,
        firecrawl=firecrawl,
        openrouter=openrouter,
        response_formatter=response_formatter,
        audit_func=_audit_func,
        sem=_get_semaphore,
    )

    _processor_instances["url_processor"] = url_processor
    _processor_instances["db"] = db
    _processor_instances["cfg"] = cfg

    return url_processor


async def process_url_request(request_id: int, db_path: str | None = None) -> None:
    """
    Process a URL request in the background.

    Args:
        request_id: ID of the request to process
        db_path: Optional database path (defaults to config value)

    This function:
    1. Loads the request from database
    2. Updates status to "processing"
    3. Extracts content via Firecrawl
    4. Generates summary via LLM
    5. Stores summary and updates status to "success"
    6. On error, updates status to "error" with error message
    """
    # Get database instance
    if db_path:
        cfg = load_config()
        db = Database(
            path=db_path,
            operation_timeout=cfg.database.operation_timeout,
            max_retries=cfg.database.max_retries,
            json_max_size=cfg.database.json_max_size,
            json_max_depth=cfg.database.json_max_depth,
            json_max_array_length=cfg.database.json_max_array_length,
            json_max_dict_keys=cfg.database.json_max_dict_keys,
        )
    else:
        await _get_url_processor()  # Initialize if needed
        db = _processor_instances["db"]

    correlation_id = f"bg-proc-{request_id}"
    lock = _get_request_lock(request_id)

    async with lock:
        try:
            # Load request
            request = RequestModel.get_by_id(request_id)
            if not request:
                logger.error(
                    f"Request {request_id} not found", extra={"correlation_id": correlation_id}
                )
                return

            # Check if already processed
            existing_summary = Summary.select().where(Summary.request == request).first()
            if existing_summary:
                logger.info(
                    f"Request {request_id} already has summary, skipping",
                    extra={"correlation_id": correlation_id},
                )
                return

            correlation_id = request.correlation_id or correlation_id
            logger.info(
                f"Starting background processing for request {request_id}",
                extra={
                    "correlation_id": correlation_id,
                    "type": request.type,
                    "url": request.input_url,
                },
            )

            # Update status to processing
            request.status = "processing"
            request.save()

            if request.type == "url":
                await _run_with_retries(
                    lambda: _process_url_type(request, db),
                    attempts=3,
                    base_delay=1.0,
                )
            elif request.type == "forward":
                await _run_with_retries(
                    lambda: _process_forward_type(request, db),
                    attempts=3,
                    base_delay=1.0,
                )
            else:
                raise ValueError(f"Unknown request type: {request.type}")

            # Update status to success
            request.status = "success"
            request.save()

            logger.info(
                f"Successfully processed request {request_id}",
                extra={"correlation_id": correlation_id},
            )

        except Exception as e:
            logger.error(
                f"Failed to process request {request_id}: {e}",
                exc_info=True,
                extra={"correlation_id": correlation_id, "error": str(e)},
            )

            # Update status to error
            try:
                request = RequestModel.get_by_id(request_id)
                if request:
                    request.status = "error"
                    request.save()
            except Exception as save_error:
                logger.error(f"Failed to update request status: {save_error}")


async def _process_url_type(request: RequestModel, db: Database) -> None:
    """Process a URL-type request."""
    from app.core.lang import choose_language
    from app.core.url_utils import normalize_url

    # Get URL processor components
    url_processor = await _get_url_processor()
    cfg = _processor_instances["cfg"]

    # Normalize URL
    normalized_url = normalize_url(request.input_url)

    # Determine language
    lang = request.lang_detected or "auto"
    if lang == "auto":
        lang = choose_language(normalized_url, None, cfg.runtime.preferred_lang)

    # Extract content
    logger.info(
        f"Extracting content for {normalized_url}", extra={"correlation_id": request.correlation_id}
    )

    extraction_result = await url_processor.content_extractor.extract(
        url=normalized_url,
        request_id=request.id,
        correlation_id=request.correlation_id,
    )

    if not extraction_result or not extraction_result.get("content"):
        raise ValueError("Content extraction failed - no content returned")

    content = extraction_result["content"]

    # Generate summary
    logger.info(
        f"Generating summary for {normalized_url}",
        extra={"correlation_id": request.correlation_id, "content_length": len(content)},
    )

    summary_result = await url_processor.llm_summarizer.summarize(
        content=content,
        lang=lang,
        request_id=request.id,
        correlation_id=request.correlation_id,
    )

    if not summary_result or not summary_result.get("summary_json"):
        raise ValueError("Summary generation failed - no summary returned")

    # Store summary in database
    summary_json = summary_result["summary_json"]

    db.upsert_summary(
        request_id=request.id,
        lang=lang,
        json_payload=summary_json,
        is_read=False,
    )

    logger.info(
        f"Summary stored successfully for request {request.id}",
        extra={"correlation_id": request.correlation_id},
    )


async def _process_forward_type(request: RequestModel, db: Database) -> None:
    """Process a forward-type request."""
    from app.core.lang import choose_language

    # Get URL processor for LLM access
    url_processor = await _get_url_processor()
    cfg = _processor_instances["cfg"]

    # Determine language
    lang = request.lang_detected or "auto"
    if lang == "auto":
        content_text = request.content_text or ""
        lang = choose_language(None, content_text, cfg.runtime.preferred_lang)

    # Generate summary from forwarded content
    logger.info(
        "Generating summary for forwarded content",
        extra={
            "correlation_id": request.correlation_id,
            "content_length": len(request.content_text or ""),
        },
    )

    summary_result = await url_processor.llm_summarizer.summarize(
        content=request.content_text or "",
        lang=lang,
        request_id=request.id,
        correlation_id=request.correlation_id,
    )

    if not summary_result or not summary_result.get("summary_json"):
        raise ValueError("Summary generation failed - no summary returned")

    # Store summary
    summary_json = summary_result["summary_json"]

    db.upsert_summary(
        request_id=request.id,
        lang=lang,
        json_payload=summary_json,
        is_read=False,
    )

    logger.info(
        f"Summary stored successfully for forwarded request {request.id}",
        extra={"correlation_id": request.correlation_id},
    )
