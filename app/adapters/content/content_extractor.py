"""Content extraction and processing for URLs."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx

from app.adapters.external.firecrawl_parser import (
    FirecrawlClient,
    FirecrawlResult,
)
from app.config import AppConfig
from app.core.html_utils import (
    clean_markdown_article_text,
    html_to_text,
    normalize_text,
)
from app.core.lang import detect_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database

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


@dataclass(slots=True)
class LowValueContentMetrics:
    """Simple container describing crawl content quality metrics."""

    char_length: int
    word_count: int
    unique_word_count: int
    top_word: str | None
    top_ratio: float
    overlay_ratio: float


@dataclass(slots=True)
class LowValueContentIssue:
    """Metadata about low-value crawl content returned by Firecrawl."""

    reason: LowValueReason
    metrics: LowValueContentMetrics
    preview: str


class ContentExtractor:
    """Handles Firecrawl operations and content extraction/processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
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

    async def extract_and_process_content(
        self,
        message: Any,
        url_text: str,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> tuple[int, str, str, str]:
        """Extract content from URL and return (req_id, content_text, content_source, detected_lang)."""
        norm = normalize_url(url_text)
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
            message, req_id, url_text, correlation_id, interaction_id, silent=silent
        )

        # Language detection
        detected = detect_language(content_text or "")
        try:
            self.db.update_request_lang_detected(req_id, detected)
        except Exception as e:  # noqa: BLE001
            logger.error("persist_lang_detected_error", extra={"error": str(e)})

        return req_id, content_text, content_source, detected

    async def _handle_request_dedupe_or_create(
        self, message: Any, url_text: str, norm: str, dedupe: str, correlation_id: str | None
    ) -> int:
        """Handle request deduplication or creation."""
        self._upsert_sender_metadata(message)

        existing_req = await self.db.async_get_request_by_dedupe_hash(dedupe)
        if not isinstance(existing_req, Mapping):
            getter = getattr(self.db, "get_request_by_dedupe_hash", None)
            existing_req = getter(dedupe) if callable(getter) else None

        if isinstance(existing_req, Mapping):
            existing_req = dict(existing_req)

        if existing_req:
            req_id = int(existing_req["id"])  # reuse existing request
            self._audit(
                "INFO",
                "url_dedupe_hit",
                {"request_id": req_id, "hash": dedupe, "url": url_text, "cid": correlation_id},
            )
            if correlation_id:
                try:
                    self.db.update_request_correlation_id(req_id, correlation_id)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "persist_cid_error", extra={"error": str(e), "cid": correlation_id}
                    )
            return req_id
        else:
            # Create new request
            return self._create_new_request(message, url_text, norm, dedupe, correlation_id)

    def _create_new_request(
        self, message: Any, url_text: str, norm: str, dedupe: str, correlation_id: str | None
    ) -> int:
        """Create a new request in the database."""
        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

        req_id = self.db.create_request(
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
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e), "cid": correlation_id})

        return req_id

    def _upsert_sender_metadata(self, message: Any) -> None:
        """Persist sender user/chat metadata for the interaction."""

        def _coerce_int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        chat_obj = getattr(message, "chat", None)
        chat_id = _coerce_int(getattr(chat_obj, "id", None) if chat_obj is not None else None)
        if chat_id is not None:
            chat_type = getattr(chat_obj, "type", None)
            chat_title = getattr(chat_obj, "title", None)
            chat_username = getattr(chat_obj, "username", None)
            try:
                self.db.upsert_chat(
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
        user_id = _coerce_int(
            getattr(from_user_obj, "id", None) if from_user_obj is not None else None
        )
        if user_id is not None:
            username = getattr(from_user_obj, "username", None)
            try:
                self.db.upsert_user(
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
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[str, str]:
        """Extract content from Firecrawl or reuse existing crawl result."""
        existing_crawl = await self.db.async_get_crawl_result_by_request(req_id)
        if not isinstance(existing_crawl, Mapping):
            getter = getattr(self.db, "get_crawl_result_by_request", None)
            existing_crawl = getter(req_id) if callable(getter) else None

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
                message, req_id, url_text, correlation_id, interaction_id, silent
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
        except Exception:
            pass

        self._audit("INFO", "reuse_crawl_result", {"request_id": None, "cid": correlation_id})

        options_obj = existing_crawl.get("options_json")
        if isinstance(options_obj, str):
            try:
                options_obj = json.loads(options_obj)
            except Exception:
                options_obj = None

        correlation_from_raw = existing_crawl.get("correlation_id")
        if not correlation_from_raw:
            raw_payload = existing_crawl.get("raw_response_json")
            if isinstance(raw_payload, dict):
                correlation_from_raw = raw_payload.get("cid")
            elif isinstance(raw_payload, str):
                try:
                    parsed_raw = json.loads(raw_payload)
                except Exception:
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
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[str, str]:
        """Perform new Firecrawl extraction."""
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
                except Exception:
                    pass

            logger.warning(
                "firecrawl_low_value_content",
                extra={
                    "cid": correlation_id,
                    "reason": reason_label,
                    **asdict(metrics),
                    "preview": quality_issue.preview,
                },
            )

        # Persist crawl result
        try:
            details_payload = Database._prepare_json_payload(crawl.response_details)
            self.db.insert_crawl_result(
                request_id=req_id,
                source_url=crawl.source_url,
                endpoint=crawl.endpoint,
                http_status=crawl.http_status,
                status=crawl.status,
                options_json=crawl.options_json,
                correlation_id=crawl.correlation_id,
                content_markdown=crawl.content_markdown,
                content_html=crawl.content_html,
                structured_json=crawl.structured_json,
                metadata_json=crawl.metadata_json,
                links_json=crawl.links_json,
                screenshots_paths_json=None,
                firecrawl_success=crawl.response_success,
                firecrawl_error_code=crawl.response_error_code,
                firecrawl_error_message=crawl.response_error_message,
                firecrawl_details_json=details_payload,
                raw_response_json=None,
                latency_ms=crawl.latency_ms,
                error_text=crawl.error_text,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_crawl_error", extra={"error": str(e), "cid": correlation_id})

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
            except Exception:
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
                try:
                    self.db.insert_crawl_result(
                        request_id=req_id,
                        source_url=salvage_crawl.source_url,
                        endpoint=salvage_crawl.endpoint,
                        http_status=salvage_crawl.http_status,
                        status=salvage_crawl.status,
                        options_json=salvage_crawl.options_json,
                        correlation_id=salvage_crawl.correlation_id,
                        content_markdown=salvage_crawl.content_markdown,
                        content_html=salvage_crawl.content_html,
                        structured_json=salvage_crawl.structured_json,
                        metadata_json=salvage_crawl.metadata_json,
                        links_json=salvage_crawl.links_json,
                        screenshots_paths_json=None,
                        firecrawl_success=salvage_crawl.response_success,
                        firecrawl_error_code=salvage_crawl.response_error_code,
                        firecrawl_error_message=salvage_crawl.response_error_message,
                        firecrawl_details_json=None,
                        raw_response_json=None,
                        latency_ms=salvage_crawl.latency_ms,
                        error_text=salvage_crawl.error_text,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "persist_salvage_crawl_error",
                        extra={"error": str(e), "cid": correlation_id},
                    )

                # Notify user we are using HTML fallback due to markdown/FC failure
                await self.response_formatter.send_html_fallback_notification(
                    message,
                    len(html_to_text(salvage_html)),
                    silent=silent,
                )

                # Continue as if crawl succeeded with HTML
                return await self._process_successful_crawl(
                    message, salvage_crawl, correlation_id, silent
                )

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
            raise ValueError(f"Firecrawl extraction failed: {failure_reason}")

        # Process successful crawl
        return await self._process_successful_crawl(message, crawl, correlation_id, silent)

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
        await self.db.async_update_request_status(req_id, "error")
        # Provide a precise, user-visible stage and context
        detail_lines = []
        url_line = crawl.source_url or "unknown"
        endpoint_line = crawl.endpoint or "/v1/scrape"
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
        except Exception:
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
        try:
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
        except Exception:
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
        except Exception:
            pass

        return content_text, content_source

    def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist message snapshot to database."""
        # Security: Validate request_id
        if not isinstance(request_id, int) or request_id <= 0:
            raise ValueError("Invalid request_id")

        # Security: Validate message object
        if message is None:
            raise ValueError("Message cannot be None")

        # Extract basic fields with best-effort approach
        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        msg_id = int(msg_id_raw) if msg_id_raw is not None else None

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        def _to_epoch(val: Any) -> int | None:
            try:
                from datetime import datetime

                if isinstance(val, datetime):
                    return int(val.timestamp())
                if val is None:
                    return None
                # Some libraries expose pyrogram types with .timestamp or int-like
                if hasattr(val, "timestamp"):
                    try:
                        ts_val = getattr(val, "timestamp")
                        if callable(ts_val):
                            return int(ts_val())
                    except Exception:
                        pass
                return int(val)  # may raise if not int-like
            except Exception:
                return None

        date_ts = _to_epoch(
            getattr(message, "date", None) or getattr(message, "forward_date", None)
        )
        text_full = getattr(message, "text", None) or getattr(message, "caption", "") or None

        # Entities
        entities_obj = list(getattr(message, "entities", []) or [])
        entities_obj.extend(list(getattr(message, "caption_entities", []) or []))
        try:

            def _ent_to_dict(e: Any) -> dict:
                if hasattr(e, "to_dict"):
                    try:
                        entity_dict = e.to_dict()
                        # Check if the result is actually serializable (not a MagicMock)
                        if isinstance(entity_dict, dict):
                            return entity_dict
                    except Exception:
                        pass
                return getattr(e, "__dict__", {})

            entities_json = [_ent_to_dict(e) for e in entities_obj]
        except Exception:
            entities_json = None

        media_type = None
        media_file_ids: list[str] = []
        # Detect common media types and collect file_ids
        try:
            if getattr(message, "photo", None) is not None:
                media_type = "photo"
                photo = getattr(message, "photo")
                fid = getattr(photo, "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "video", None) is not None:
                media_type = "video"
                fid = getattr(getattr(message, "video"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "document", None) is not None:
                media_type = "document"
                fid = getattr(getattr(message, "document"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "audio", None) is not None:
                media_type = "audio"
                fid = getattr(getattr(message, "audio"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "voice", None) is not None:
                media_type = "voice"
                fid = getattr(getattr(message, "voice"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "animation", None) is not None:
                media_type = "animation"
                fid = getattr(getattr(message, "animation"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "sticker", None) is not None:
                media_type = "sticker"
                fid = getattr(getattr(message, "sticker"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
        except Exception:
            pass

        # Filter out non-string values (like MagicMock objects) from media_file_ids
        valid_media_file_ids = [fid for fid in media_file_ids if isinstance(fid, str)]
        media_file_ids_json = valid_media_file_ids or None

        # Forward info
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_chat_id_raw = getattr(fwd_chat, "id", 0) if fwd_chat is not None else None
        forward_from_chat_id = int(fwd_chat_id_raw) if fwd_chat_id_raw is not None else None
        forward_from_chat_type = getattr(fwd_chat, "type", None)
        forward_from_chat_title = getattr(fwd_chat, "title", None)

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        forward_from_message_id = int(fwd_msg_id_raw) if fwd_msg_id_raw is not None else None
        forward_date_ts = _to_epoch(getattr(message, "forward_date", None))

        # Raw JSON if possible
        raw_json = None
        try:
            if hasattr(message, "to_dict"):
                message_dict = message.to_dict()
                # Check if the result is actually serializable (not a MagicMock)
                if isinstance(message_dict, dict):
                    raw_json = message_dict
                else:
                    raw_json = None
            else:
                raw_json = None
        except Exception:
            raw_json = None

        self.db.insert_telegram_message(
            request_id=request_id,
            message_id=msg_id,
            chat_id=chat_id,
            date_ts=date_ts,
            text_full=text_full,
            entities_json=entities_json,
            media_type=media_type,
            media_file_ids_json=media_file_ids_json,
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_type=forward_from_chat_type,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            forward_date_ts=forward_date_ts,
            telegram_raw_json=raw_json,
        )
