"""Content extraction and processing for URLs."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.external.firecrawl_parser import FirecrawlClient, FirecrawlResult
from app.adapters.telegram.message_persistence import MessagePersistence
from app.config import AppConfig
from app.core.async_utils import raise_if_cancelled
from app.core.html_utils import clean_markdown_article_text, html_to_text, normalize_text
from app.core.lang import detect_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.session import DatabaseSessionManager
from app.db.utils import prepare_json_payload
from app.infrastructure.cache.redis_cache import RedisCache

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

# Route versioning constants
URL_ROUTE_VERSION = 1

LowValueReason = Literal[
    "empty_after_cleaning",
    "overlay_content_detected",
    "content_too_short",
    "content_low_variation",
    "content_high_repetition",
]


class LowValueContentMetrics(BaseModel):
    """Simple container describing crawl content quality metrics."""

    model_config = ConfigDict(frozen=True)

    char_length: int = Field(ge=0)
    word_count: int = Field(ge=0)
    unique_word_count: int = Field(ge=0)
    top_word: str | None = None
    top_ratio: float = Field(ge=0.0, le=1.0)
    overlay_ratio: float = Field(ge=0.0, le=1.0)


class LowValueContentIssue(BaseModel):
    """Metadata about low-value crawl content returned by Firecrawl."""

    model_config = ConfigDict(frozen=True)

    reason: LowValueReason
    metrics: LowValueContentMetrics
    preview: str


class ContentExtractor:
    """Handles Firecrawl operations and content extraction/processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        firecrawl: FirecrawlClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.firecrawl = firecrawl
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self._cache = RedisCache(cfg)
        self.message_persistence = MessagePersistence(db)

    def _schedule_crawl_persistence(
        self, req_id: int, crawl: FirecrawlResult, correlation_id: str | None
    ) -> asyncio.Task[None] | None:
        """Run crawl persistence off the network path and log any errors."""
        try:
            task: asyncio.Task[None] = asyncio.create_task(
                self._persist_crawl_result(req_id, crawl, correlation_id)
            )
        except RuntimeError as exc:
            logger.error(
                "persist_crawl_schedule_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return None

        def _log_task_error(t: asyncio.Task[None]) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "persist_crawl_task_error",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

    async def _persist_crawl_result(
        self, req_id: int, crawl: FirecrawlResult, correlation_id: str | None
    ) -> None:
        """Persist crawl result with error logging."""
        try:
            await self.message_persistence.crawl_repo.async_insert_crawl_result(
                request_id=req_id,
                success=crawl.response_success,
                markdown=crawl.content_markdown,
                error=crawl.error_text,
                metadata_json=crawl.metadata_json,
            )
        except Exception as e:  # noqa: BLE001
            raise_if_cancelled(e)
            logger.error("persist_crawl_error", extra={"error": str(e), "cid": correlation_id})

    async def _await_persistence_task(self, task: asyncio.Task[None] | None) -> None:
        """Await a scheduled persistence task, logging any errors."""
        if task is None:
            return
        try:
            await task
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.error("persist_crawl_task_error", extra={"error": str(exc)})

    async def extract_content_pure(
        self,
        url: str,
        correlation_id: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Pure extraction method without message dependencies.

        This method performs content extraction without requiring a Telegram message
        object or sending notifications. Suitable for use by agents and standalone tools.

        Args:
            url: URL to extract content from
            correlation_id: Optional correlation ID for tracing

        Returns:
            Tuple of (content_text, content_source, metadata) where:
            - content_text: Extracted and cleaned content
            - content_source: Source of content ("markdown", "html", or "none")
            - metadata: Dictionary with extraction metadata

        Raises:
            ValueError: If extraction fails
        """
        normalized_url = normalize_url(url)

        logger.info(
            "pure_extraction_start",
            extra={"url": url, "normalized": normalized_url, "cid": correlation_id},
        )

        # Perform Firecrawl scrape
        async with self._sem():
            crawl = await self.firecrawl.scrape_markdown(url, request_id=None)

        # Check content quality
        quality_issue = self._detect_low_value_content(crawl)
        if quality_issue:
            error_msg = f"Low-value content detected: {quality_issue.reason}"
            logger.warning(
                "pure_extraction_low_value",
                extra={"cid": correlation_id, "reason": quality_issue.reason},
            )
            raise ValueError(error_msg) from None

        # Validate crawl success
        has_markdown = bool(crawl.content_markdown and crawl.content_markdown.strip())
        has_html = bool(crawl.content_html and crawl.content_html.strip())

        if crawl.status != "ok" or not (has_markdown or has_html):
            # Try direct HTML salvage
            try:
                salvage_html = await self._attempt_direct_html_salvage(url)
                if salvage_html:
                    content_text = html_to_text(salvage_html)
                    content_source = "html"
                    metadata = {
                        "extraction_method": "direct_fetch",
                        "http_status": 200,
                        "salvaged": True,
                    }

                    logger.info(
                        "pure_extraction_salvaged",
                        extra={"cid": correlation_id, "content_len": len(content_text)},
                    )

                    return content_text, content_source, metadata
            except Exception as e:
                raise_if_cancelled(e)
                # Salvage attempt failed, continue to error handling
                pass

            error_msg = crawl.error_text or "Firecrawl extraction failed"
            raise ValueError(f"Extraction failed: {error_msg}") from None

        # Process successful crawl
        if crawl.content_markdown and crawl.content_markdown.strip():
            content_text = clean_markdown_article_text(crawl.content_markdown)
            content_source = "markdown"
        elif crawl.content_html and crawl.content_html.strip():
            content_text = html_to_text(crawl.content_html)
            content_source = "html"
        else:
            content_text = ""
            content_source = "none"

        # Build metadata
        metadata = {
            "extraction_method": "firecrawl",
            "http_status": crawl.http_status,
            "endpoint": crawl.endpoint,
            "latency_ms": crawl.latency_ms,
            "content_length": len(content_text),
            "source_format": content_source,
        }

        # Add Firecrawl metadata if available
        if crawl.metadata_json:
            metadata["firecrawl_metadata"] = crawl.metadata_json

        logger.info(
            "pure_extraction_success",
            extra={
                "cid": correlation_id,
                "content_len": len(content_text),
                "source": content_source,
            },
        )

        return content_text, content_source, metadata

    async def extract_and_process_content(
        self,
        message: Any,
        url_text: str,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> tuple[int, str, str, str]:
        """Extract content from URL and return (req_id, content_text, content_source, detected_lang)."""
        from app.core.url_utils import is_youtube_url

        norm = normalize_url(url_text)

        # Check if YouTube URL and route accordingly
        if is_youtube_url(norm):
            logger.info(
                "youtube_url_detected",
                extra={"url": url_text, "normalized": norm, "cid": correlation_id},
            )
            return await self._extract_youtube_content(
                message, url_text, norm, correlation_id, interaction_id, silent
            )

        # Regular web content flow
        dedupe = url_hash_sha256(norm)

        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm, "hash": dedupe, "cid": correlation_id},
        )

        # Notify: request accepted with URL preview
        await self.response_formatter.send_url_accepted_notification(
            message, norm, correlation_id, silent=silent
        )

        # Handle request deduplication and creation
        req_id = await self._handle_request_dedupe_or_create(
            message, url_text, norm, dedupe, correlation_id
        )

        # Extract content from Firecrawl or reuse existing
        content_text, content_source = await self._extract_or_reuse_content(
            message,
            req_id,
            url_text,
            dedupe,
            correlation_id,
            interaction_id,
            silent=silent,
        )

        # Language detection
        detected = detect_language(content_text or "")
        try:
            await self.message_persistence.request_repo.async_update_request_lang_detected(
                req_id, detected
            )
        except Exception as e:  # noqa: BLE001
            raise_if_cancelled(e)
            logger.error("persist_lang_detected_error", extra={"error": str(e)})

        return req_id, content_text, content_source, detected

    async def _handle_request_dedupe_or_create(
        self, message: Any, url_text: str, norm: str, dedupe: str, correlation_id: str | None
    ) -> int:
        """Handle request deduplication or creation with race condition protection.

        This method implements proper handling for concurrent requests with the same URL.
        Uses optimistic concurrency: try to create, fall back to fetch on collision.

        Returns:
            Request ID (either existing or newly created)
        """
        await self._upsert_sender_metadata(message)

        # Optimistic approach: Try to create first, handle collision if it occurs
        # This is more efficient than always checking first (avoids extra DB query)
        try:
            # Attempt to create new request
            req_id = await self._create_new_request(message, url_text, norm, dedupe, correlation_id)

            # If we get here, creation succeeded (new URL)
            self._audit(
                "INFO",
                "url_request_created",
                {"request_id": req_id, "hash": dedupe, "url": url_text, "cid": correlation_id},
            )
            return req_id

        except Exception as create_error:
            # If creation failed due to race condition, fetch the existing request
            # This handles the case where another thread created the request between
            # our check and insert
            logger.debug(
                "url_request_creation_failed_fetching_existing",
                extra={
                    "error": str(create_error),
                    "error_type": type(create_error).__name__,
                    "cid": correlation_id,
                },
            )

            # Fetch existing request by dedupe hash
            existing_req = (
                await self.message_persistence.request_repo.async_get_request_by_dedupe_hash(dedupe)
            )

            if isinstance(existing_req, Mapping):
                existing_req = dict(existing_req)

            if existing_req:
                req_id = int(existing_req["id"])
                self._audit(
                    "INFO",
                    "url_dedupe_hit_after_race",
                    {
                        "request_id": req_id,
                        "hash": dedupe,
                        "url": url_text,
                        "cid": correlation_id,
                    },
                )

                # Update correlation ID for the existing request
                if correlation_id:
                    try:
                        await self.message_persistence.request_repo.async_update_request_correlation_id(
                            req_id, correlation_id
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.error(
                            "persist_cid_error", extra={"error": str(e), "cid": correlation_id}
                        )
                return req_id

            # If we still can't find existing request, something is wrong
            # Re-raise the original error
            logger.error(
                "url_request_race_condition_unresolved",
                extra={
                    "error": str(create_error),
                    "dedupe_hash": dedupe,
                    "cid": correlation_id,
                },
            )
            raise create_error

    async def _create_new_request(
        self, message: Any, url_text: str, norm: str, dedupe: str, correlation_id: str | None
    ) -> int:
        """Create a new request in the database."""
        from app.core.validation import (
            safe_message_id,
            safe_telegram_chat_id,
            safe_telegram_user_id,
        )

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = safe_telegram_chat_id(chat_id_raw, field_name="chat_id")

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = safe_telegram_user_id(user_id_raw, field_name="user_id")

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = safe_message_id(msg_id_raw, field_name="message_id")

        req_id = await self.message_persistence.request_repo.async_create_request(
            type_="url",
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_url=url_text,
            normalized_url=norm,
            dedupe_hash=dedupe,
            input_message_id=input_message_id,
            content_text=url_text,  # Store the URL as content text for consistency
            route_version=URL_ROUTE_VERSION,
        )

        # Snapshot telegram message (only on first request for this URL)
        try:
            await self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            raise_if_cancelled(e)
            logger.error("snapshot_error", extra={"error": str(e), "cid": correlation_id})

        return req_id

    async def _upsert_sender_metadata(self, message: Any) -> None:
        """Persist sender user/chat metadata for the interaction."""
        from app.core.validation import safe_telegram_chat_id, safe_telegram_user_id

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", None) if chat_obj is not None else None
        chat_id = safe_telegram_chat_id(chat_id_raw, field_name="chat_id")
        if chat_id is not None:
            chat_type = getattr(chat_obj, "type", None)
            chat_title = getattr(chat_obj, "title", None)
            chat_username = getattr(chat_obj, "username", None)
            try:
                await self.message_persistence.user_repo.async_upsert_chat(
                    chat_id=chat_id,
                    type_=str(chat_type) if chat_type is not None else None,
                    title=str(chat_title) if isinstance(chat_title, str) else None,
                    username=str(chat_username) if isinstance(chat_username, str) else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "chat_upsert_failed",
                    extra={"chat_id": chat_id, "error": str(exc)},
                )

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", None) if from_user_obj is not None else None
        user_id = safe_telegram_user_id(user_id_raw, field_name="user_id")
        if user_id is not None:
            username = getattr(from_user_obj, "username", None)
            try:
                await self.message_persistence.user_repo.async_upsert_user(
                    telegram_user_id=user_id,
                    username=str(username) if isinstance(username, str) else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "user_upsert_failed",
                    extra={"user_id": user_id, "error": str(exc)},
                )

    async def _extract_or_reuse_content(
        self,
        message: Any,
        req_id: int,
        url_text: str,
        dedupe_hash: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[str, str]:
        """Extract content from Firecrawl or reuse existing crawl result."""
        existing_crawl = (
            await self.message_persistence.crawl_repo.async_get_crawl_result_by_request(req_id)
        )

        if isinstance(existing_crawl, Mapping):
            existing_crawl = dict(existing_crawl)

        if existing_crawl and (
            existing_crawl.get("content_markdown") or existing_crawl.get("content_html")
        ):
            return await self._process_existing_crawl(
                message, existing_crawl, correlation_id, silent
            )
        else:
            return await self._perform_new_crawl(
                message,
                req_id,
                url_text,
                dedupe_hash,
                correlation_id,
                interaction_id,
                silent,
            )

    async def _process_existing_crawl(
        self, message: Any, existing_crawl: dict, correlation_id: str | None, silent: bool = False
    ) -> tuple[str, str]:
        """Process existing crawl result."""
        md = existing_crawl.get("content_markdown")
        html = existing_crawl.get("content_html")

        # Process content with HTML fallback for empty markdown
        if md and md.strip():
            content_text = clean_markdown_article_text(md)
            content_source = "markdown"
        elif html and html.strip():
            content_text = html_to_text(html)
            content_source = "html"
            logger.info(
                "html_fallback_used_existing",
                extra={
                    "cid": correlation_id,
                    "reason": "markdown_empty_or_missing",
                    "html_len": len(html),
                    "cleaned_text_len": len(content_text),
                },
            )
        else:
            content_text = ""
            content_source = "none"

        # Optional normalization (feature-flagged)
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                content_text = normalize_text(content_text)
        except (AttributeError, RuntimeError):
            pass

        self._audit("INFO", "reuse_crawl_result", {"request_id": None, "cid": correlation_id})

        options_obj = existing_crawl.get("options_json")
        if isinstance(options_obj, str):
            try:
                options_obj = json.loads(options_obj)
            except (json.JSONDecodeError, ValueError):
                options_obj = None

        correlation_from_raw = existing_crawl.get("correlation_id")
        if not correlation_from_raw:
            raw_payload = existing_crawl.get("raw_response_json")
            if isinstance(raw_payload, dict):
                correlation_from_raw = raw_payload.get("cid")
            elif isinstance(raw_payload, str):
                try:
                    parsed_raw = json.loads(raw_payload)
                except (json.JSONDecodeError, ValueError):
                    parsed_raw = None
                if isinstance(parsed_raw, dict):
                    correlation_from_raw = parsed_raw.get("cid")

        latency_val = existing_crawl.get("latency_ms")
        latency_sec = (latency_val / 1000.0) if isinstance(latency_val, int | float) else None

        await self.response_formatter.send_content_reuse_notification(
            message,
            http_status=existing_crawl.get("http_status"),
            crawl_status=existing_crawl.get("status"),
            latency_sec=latency_sec,
            correlation_id=correlation_from_raw,
            options=options_obj,
            silent=silent,
        )

        return content_text, content_source

    async def _perform_new_crawl(
        self,
        message: Any,
        req_id: int,
        url_text: str,
        dedupe_hash: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[str, str]:
        """Perform new Firecrawl extraction."""
        persist_task: asyncio.Task[None] | None = None

        cached_crawl = await self._get_cached_crawl(dedupe_hash, correlation_id)
        if cached_crawl:
            logger.info(
                "firecrawl_cache_hit",
                extra={
                    "cid": correlation_id,
                    "hash": dedupe_hash,
                    "endpoint": cached_crawl.endpoint,
                },
            )
            options_obj = (
                cached_crawl.options_json if isinstance(cached_crawl.options_json, dict) else None
            )
            await self.response_formatter.send_content_reuse_notification(
                message,
                http_status=cached_crawl.http_status,
                crawl_status=cached_crawl.status,
                latency_sec=None,
                correlation_id=cached_crawl.correlation_id,
                options=options_obj,
                silent=silent,
            )
            persist_task = self._schedule_crawl_persistence(req_id, cached_crawl, correlation_id)
            result = await self._process_successful_crawl(
                message, cached_crawl, correlation_id, silent
            )
            await self._await_persistence_task(persist_task)
            return result

        # Notify: starting Firecrawl with progress indicator
        await self.response_formatter.send_firecrawl_start_notification(
            message, url=url_text, silent=silent
        )

        async with self._sem():
            crawl = await self.firecrawl.scrape_markdown(url_text, request_id=req_id)

        quality_issue = self._detect_low_value_content(crawl)
        if quality_issue:
            metrics = quality_issue.metrics
            reason_label = quality_issue.reason
            metric_parts = [
                f"chars={metrics.char_length}",
                f"words={metrics.word_count}",
                f"unique={metrics.unique_word_count}",
            ]
            if metrics.top_word:
                metric_parts.append(
                    f"top_word={metrics.top_word}, top_ratio={metrics.top_ratio:.2f}"
                )
            metric_parts.append(f"overlay_ratio={metrics.overlay_ratio:.2f}")
            metric_str = ", ".join(metric_parts)

            crawl.status = "error"
            crawl.error_text = f"insufficient_useful_content:{reason_label} ({metric_str})"

            if self._audit:
                try:
                    audit_payload = {
                        "request_id": req_id,
                        "cid": correlation_id,
                        "reason": reason_label,
                        "char_length": metrics.char_length,
                        "word_count": metrics.word_count,
                        "unique_word_count": metrics.unique_word_count,
                        "overlay_ratio": round(metrics.overlay_ratio, 3),
                    }
                    if metrics.top_word:
                        audit_payload["top_word"] = metrics.top_word
                        audit_payload["top_ratio"] = round(metrics.top_ratio, 3)
                    self._audit("WARNING", "firecrawl_low_value_content", audit_payload)
                except (RuntimeError, ValueError, TypeError):
                    pass

            logger.warning(
                "firecrawl_low_value_content",
                extra={
                    "cid": correlation_id,
                    "reason": reason_label,
                    **metrics.model_dump(),
                    "preview": quality_issue.preview,
                },
            )

        # Persist crawl result
        persist_task = self._schedule_crawl_persistence(req_id, crawl, correlation_id)

        # Debug logging for crawl result
        logger.debug(
            "crawl_result_debug",
            extra={
                "cid": correlation_id,
                "status": crawl.status,
                "http_status": crawl.http_status,
                "error_text": crawl.error_text,
                "has_markdown": bool(crawl.content_markdown),
                "has_html": bool(crawl.content_html),
                "markdown_len": len(crawl.content_markdown) if crawl.content_markdown else 0,
                "html_len": len(crawl.content_html) if crawl.content_html else 0,
            },
        )

        # Validate crawl result
        has_markdown = bool(crawl.content_markdown and crawl.content_markdown.strip())
        has_html = bool(crawl.content_html and crawl.content_html.strip())

        if quality_issue:
            has_markdown = False
            has_html = False

        if crawl.status != "ok" or not (has_markdown or has_html):
            # Attempt a direct HTML fetch salvage before failing
            try:
                salvage_html = await self._attempt_direct_html_salvage(url_text)
            except (OSError, TimeoutError, RuntimeError):
                salvage_html = None

            if salvage_html:
                logger.info(
                    "direct_html_salvage_success",
                    extra={
                        "cid": correlation_id,
                        "html_len": len(salvage_html or ""),
                        "reason": (crawl.error_text or "no_content_from_firecrawl"),
                    },
                )

                salvage_crawl = FirecrawlResult(
                    status="ok",
                    http_status=200,
                    content_markdown=None,
                    content_html=salvage_html,
                    structured_json=None,
                    metadata_json=None,
                    links_json=None,
                    response_success=None,
                    response_error_code=None,
                    response_error_message=None,
                    response_details=None,
                    latency_ms=None,
                    error_text=None,
                    source_url=url_text,
                    endpoint="direct_fetch",
                    options_json={"direct_fetch": True},
                    correlation_id=None,
                )

                # Persist salvage crawl result (separate entry)
                salvage_persist_task = self._schedule_crawl_persistence(
                    req_id, salvage_crawl, correlation_id
                )

                # Notify user we are using HTML fallback due to markdown/FC failure
                await self.response_formatter.send_html_fallback_notification(
                    message,
                    len(html_to_text(salvage_html)),
                    silent=silent,
                )

                # Continue as if crawl succeeded with HTML
                result = await self._process_successful_crawl(
                    message, salvage_crawl, correlation_id, silent
                )
                await self._write_firecrawl_cache(dedupe_hash, salvage_crawl)
                await self._await_persistence_task(salvage_persist_task)
                return result

            await self._await_persistence_task(persist_task)
            await self._handle_crawl_error(
                message,
                req_id,
                crawl,
                correlation_id,
                interaction_id,
                has_markdown,
                has_html,
                silent,
            )
            failure_reason = crawl.error_text or "Firecrawl extraction failed"
            raise ValueError(f"Firecrawl extraction failed: {failure_reason}") from None

        # Process successful crawl
        result = await self._process_successful_crawl(message, crawl, correlation_id, silent)
        await self._write_firecrawl_cache(dedupe_hash, crawl)
        return result

    def _detect_low_value_content(self, crawl: FirecrawlResult) -> LowValueContentIssue | None:
        """Detect low-value Firecrawl responses that should halt processing."""

        text_candidates: list[str] = []
        if crawl.content_markdown and crawl.content_markdown.strip():
            text_candidates.append(clean_markdown_article_text(crawl.content_markdown))
        if crawl.content_html and crawl.content_html.strip():
            text_candidates.append(html_to_text(crawl.content_html))

        primary_text = next((t for t in text_candidates if t and t.strip()), "")
        normalized = re.sub(r"\s+", " ", primary_text).strip()

        words_raw = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ']+", normalized)
        words = [w.lower() for w in words_raw if w]
        word_count = len(words)
        unique_word_count = len(set(words))

        top_word: str | None = None
        top_ratio = 0.0
        if words:
            counter = Counter(words)
            top_word, top_count = counter.most_common(1)[0]
            top_ratio = top_count / word_count if word_count else 0.0

        overlay_terms = {
            "accept",
            "close",
            "cookie",
            "cookies",
            "consent",
            "login",
            "signin",
            "signup",
            "subscribe",
        }
        overlay_hits = sum(1 for w in words if w in overlay_terms)
        overlay_ratio = overlay_hits / word_count if word_count else 0.0

        metrics = LowValueContentMetrics(
            char_length=len(normalized),
            word_count=word_count,
            unique_word_count=unique_word_count,
            top_word=top_word,
            top_ratio=top_ratio,
            overlay_ratio=overlay_ratio,
        )

        reason: LowValueReason | None = None
        if not normalized or word_count == 0:
            reason = "empty_after_cleaning"
        elif overlay_ratio >= 0.7 and len(normalized) < 600:
            reason = "overlay_content_detected"
        elif len(normalized) < 48 and word_count <= 2:
            reason = "content_too_short"
        elif len(normalized) < 120 and (
            unique_word_count <= 3 or (word_count >= 4 and top_ratio >= 0.8)
        ):
            reason = "content_low_variation"
        elif word_count >= 6 and top_ratio >= 0.92:
            reason = "content_high_repetition"

        if reason:
            preview = normalized[:200]
            return LowValueContentIssue(reason=reason, metrics=metrics, preview=preview)

        return None

    async def _get_cached_crawl(
        self, dedupe_hash: str, correlation_id: str | None
    ) -> FirecrawlResult | None:
        """Fetch a cached Firecrawl result if available and valid."""
        if not self._cache.enabled:
            return None

        cached = await self._cache.get_json("fc", str(URL_ROUTE_VERSION), dedupe_hash)
        if not isinstance(cached, dict):
            return None

        try:
            crawl = FirecrawlResult(**cached)
        except Exception as exc:
            logger.warning(
                "firecrawl_cache_invalid",
                extra={
                    "cid": correlation_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return None

        if self._detect_low_value_content(crawl):
            logger.debug(
                "firecrawl_cache_low_value_skipped",
                extra={"cid": correlation_id, "hash": dedupe_hash},
            )
            return None

        return crawl

    async def _write_firecrawl_cache(self, dedupe_hash: str, crawl: FirecrawlResult) -> None:
        """Persist Firecrawl response into Redis cache."""
        if not self._cache.enabled:
            return
        if crawl.status != "ok":
            return

        has_markdown = bool(crawl.content_markdown and crawl.content_markdown.strip())
        has_html = bool(crawl.content_html and crawl.content_html.strip())
        if not (has_markdown or has_html):
            return

        payload = crawl.model_dump()
        await self._cache.set_json(
            value=payload,
            ttl_seconds=getattr(self.cfg.redis, "firecrawl_ttl_seconds", 21_600),
            parts=("fc", str(URL_ROUTE_VERSION), dedupe_hash),
        )

    async def _handle_crawl_error(
        self,
        message: Any,
        req_id: int,
        crawl: FirecrawlResult,
        correlation_id: str | None,
        interaction_id: int | None,
        has_markdown: bool,
        has_html: bool,
        silent: bool = False,
    ) -> None:
        """Handle Firecrawl extraction errors."""
        await self.message_persistence.request_repo.async_update_request_status(req_id, "error")
        # Provide a precise, user-visible stage and context
        detail_lines = []
        url_line = crawl.source_url or "unknown"
        endpoint_line = crawl.endpoint or "/v2/scrape"
        http_line = str(crawl.http_status) if crawl.http_status is not None else "n/a"
        err_line = crawl.error_text or "unknown"
        content_hint = f"md:{int(has_markdown)} html:{int(has_html)}"
        detail_lines.append(f"🔗 URL: {url_line}")
        detail_lines.append(f"🧭 Stage: Firecrawl scrape ({endpoint_line})")
        detail_lines.append(f"📶 HTTP: {http_line}")
        detail_lines.append(f"⚠️ Error: {err_line}")
        detail_lines.append(f"🧩 Content received: {content_hint}")

        await self.response_formatter.send_error_notification(
            message, "firecrawl_error", correlation_id, details="\n".join(detail_lines)
        )

        logger.error(
            "firecrawl_error",
            extra={
                "error": crawl.error_text,
                "cid": correlation_id,
                "status": crawl.status,
                "http_status": crawl.http_status,
                "has_markdown": has_markdown,
                "has_html": has_html,
            },
        )

        try:
            self._audit(
                "ERROR",
                "firecrawl_error",
                {"request_id": req_id, "cid": correlation_id, "error": crawl.error_text},
            )
        except (RuntimeError, ValueError, TypeError):
            pass

        # Update interaction with error
        if interaction_id:
            # Note: This would need to be passed back to the caller to update
            pass

    async def _attempt_direct_html_salvage(self, url: str) -> str | None:
        """Try to fetch raw HTML directly and validate it contains readable text.

        Returns the raw HTML string if the page appears readable; otherwise None.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
        }
        timeout = max(5, int(getattr(self.cfg.runtime, "request_timeout_sec", 30)))
        overall_timeout = timeout + 5  # Add buffer for connection setup/teardown

        try:
            # Wrap entire operation in timeout to prevent indefinite hangs
            async def _fetch_html() -> str | None:
                async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                    resp = await client.get(url, headers=headers)
                    ctype = resp.headers.get("content-type", "").lower()
                    if resp.status_code != 200 or "text/html" not in ctype:
                        return None
                    html = resp.text or ""
                    # Validate that extracted text is sufficiently long to be useful
                    text_preview = html_to_text(html)
                    if len(text_preview) < 400:
                        return None
                    return html

            return await asyncio.wait_for(_fetch_html(), timeout=overall_timeout)
        except TimeoutError:
            logger.warning(
                "direct_html_salvage_timeout",
                extra={"url": url, "timeout": overall_timeout},
            )
            return None
        except Exception as e:
            raise_if_cancelled(e)
            logger.debug(
                "direct_html_salvage_failed",
                extra={"url": url, "error": str(e), "error_type": type(e).__name__},
            )
            return None

    async def _process_successful_crawl(
        self,
        message: Any,
        crawl: FirecrawlResult,
        correlation_id: str | None,
        silent: bool = False,
    ) -> tuple[str, str]:
        """Process successful Firecrawl result."""
        # Notify: Firecrawl success
        excerpt_len = (len(crawl.content_markdown) if crawl.content_markdown else 0) or (
            len(crawl.content_html) if crawl.content_html else 0
        )
        latency_sec = (crawl.latency_ms or 0) / 1000.0
        await self.response_formatter.send_firecrawl_success_notification(
            message,
            excerpt_len,
            latency_sec,
            http_status=crawl.http_status,
            crawl_status=crawl.status,
            correlation_id=crawl.correlation_id,
            endpoint=crawl.endpoint,
            options=crawl.options_json,
            silent=silent,
        )

        # Process content with HTML fallback for empty markdown
        if crawl.content_markdown and crawl.content_markdown.strip():
            content_text = clean_markdown_article_text(crawl.content_markdown)
            content_source = "markdown"
        elif crawl.content_html and crawl.content_html.strip():
            content_text = html_to_text(crawl.content_html)
            content_source = "html"
            logger.info(
                "html_fallback_used",
                extra={
                    "cid": correlation_id,
                    "reason": "markdown_empty_or_missing",
                    "html_len": len(crawl.content_html),
                    "cleaned_text_len": len(content_text),
                },
            )
            # Notify user that HTML fallback was used
            await self.response_formatter.send_html_fallback_notification(
                message, len(content_text), silent=silent
            )
        else:
            # This should not happen due to validation above, but handle gracefully
            content_text = ""
            content_source = "none"
            logger.error(
                "no_content_available",
                extra={
                    "cid": correlation_id,
                    "markdown_len": len(crawl.content_markdown) if crawl.content_markdown else 0,
                    "html_len": len(crawl.content_html) if crawl.content_html else 0,
                },
            )

        # Optional normalization (feature-flagged)
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                content_text = normalize_text(content_text)
        except (AttributeError, RuntimeError):
            pass

        return content_text, content_source

    async def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist message snapshot to database."""
        await self.message_persistence.persist_message_snapshot(request_id, message)

    async def _extract_youtube_content(
        self,
        message: Any,
        url_text: str,
        norm: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[int, str, str, str]:
        """Extract YouTube video transcript and download video.

        Returns:
            (req_id, transcript_text, content_source, detected_lang)
        """
        from app.adapters.youtube.youtube_downloader import YouTubeDownloader

        # Check if YouTube download is enabled
        if not self.cfg.youtube.enabled:
            logger.warning(
                "youtube_download_disabled",
                extra={"url": url_text, "cid": correlation_id},
            )
            raise ValueError("YouTube video download is disabled in configuration")

        # Initialize YouTube downloader
        youtube_downloader = YouTubeDownloader(
            cfg=self.cfg,
            db=self.db,
            response_formatter=self.response_formatter,
            audit_func=self._audit,
        )

        # Download video and extract transcript
        try:
            (
                req_id,
                transcript_text,
                content_source,
                detected_lang,
                video_metadata,
            ) = await youtube_downloader.download_and_extract(
                message, url_text, correlation_id, interaction_id, silent
            )

            logger.info(
                "youtube_extraction_complete",
                extra={
                    "video_id": video_metadata.get("video_id"),
                    "request_id": req_id,
                    "transcript_length": len(transcript_text),
                    "cid": correlation_id,
                },
            )

            return req_id, transcript_text, content_source, detected_lang

        except Exception as e:
            raise_if_cancelled(e)
            logger.exception(
                "youtube_extraction_failed",
                extra={"url": url_text, "error": str(e), "cid": correlation_id},
            )
            raise
