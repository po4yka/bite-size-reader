"""Content extraction and processing for URLs."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.external.firecrawl_parser import FirecrawlClient, FirecrawlResult
from app.config import AppConfig
from app.core.html_utils import (
    clean_markdown_article_text,
    html_to_text,
    normalize_with_textacy,
)
from app.core.lang import detect_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

# Route versioning constants
URL_ROUTE_VERSION = 1


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
    ) -> tuple[int, str, str, str]:
        """Extract content from URL and return (req_id, content_text, content_source, detected_lang)."""
        norm = normalize_url(url_text)
        dedupe = url_hash_sha256(norm)

        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm, "hash": dedupe, "cid": correlation_id},
        )

        # Notify: request accepted with URL preview
        await self.response_formatter.send_url_accepted_notification(message, norm, correlation_id)

        # Handle request deduplication and creation
        req_id = await self._handle_request_dedupe_or_create(
            message, url_text, norm, dedupe, correlation_id
        )

        # Extract content from Firecrawl or reuse existing
        content_text, content_source = await self._extract_or_reuse_content(
            message, req_id, url_text, correlation_id, interaction_id
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
        existing_req = self.db.get_request_by_dedupe_hash(dedupe)

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
            route_version=URL_ROUTE_VERSION,
        )

        # Snapshot telegram message (only on first request for this URL)
        try:
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e), "cid": correlation_id})

        return req_id

    async def _extract_or_reuse_content(
        self,
        message: Any,
        req_id: int,
        url_text: str,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> tuple[str, str]:
        """Extract content from Firecrawl or reuse existing crawl result."""
        existing_crawl = self.db.get_crawl_result_by_request(req_id)

        if existing_crawl and (
            existing_crawl.get("content_markdown") or existing_crawl.get("content_html")
        ):
            return await self._process_existing_crawl(message, existing_crawl, correlation_id)
        else:
            return await self._perform_new_crawl(
                message, req_id, url_text, correlation_id, interaction_id
            )

    async def _process_existing_crawl(
        self, message: Any, existing_crawl: dict, correlation_id: str | None
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
                content_text = normalize_with_textacy(content_text)
        except Exception:
            pass

        self._audit("INFO", "reuse_crawl_result", {"request_id": None, "cid": correlation_id})

        options_obj = None
        correlation_from_raw = existing_crawl.get("correlation_id")
        try:
            options_raw = existing_crawl.get("options_json")
            if options_raw:
                options_obj = json.loads(options_raw)
        except Exception:
            options_obj = None

        if not correlation_from_raw:
            try:
                raw_payload = existing_crawl.get("raw_response_json")
                if raw_payload:
                    parsed_raw = json.loads(raw_payload)
                    if isinstance(parsed_raw, dict):
                        correlation_from_raw = parsed_raw.get("cid")
            except Exception:
                correlation_from_raw = None

        latency_val = existing_crawl.get("latency_ms")
        latency_sec = (latency_val / 1000.0) if isinstance(latency_val, int | float) else None

        await self.response_formatter.send_content_reuse_notification(
            message,
            http_status=existing_crawl.get("http_status"),
            crawl_status=existing_crawl.get("status"),
            latency_sec=latency_sec,
            correlation_id=correlation_from_raw,
            options=options_obj,
        )

        return content_text, content_source

    async def _perform_new_crawl(
        self,
        message: Any,
        req_id: int,
        url_text: str,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> tuple[str, str]:
        """Perform new Firecrawl extraction."""
        # Notify: starting Firecrawl with progress indicator
        await self.response_formatter.send_firecrawl_start_notification(message)

        async with self._sem():
            crawl = await self.firecrawl.scrape_markdown(url_text, request_id=req_id)

        # Persist crawl result
        try:
            self.db.insert_crawl_result(
                request_id=req_id,
                source_url=crawl.source_url,
                endpoint=crawl.endpoint,
                http_status=crawl.http_status,
                status=crawl.status,
                options_json=json.dumps(crawl.options_json or {}),
                correlation_id=crawl.correlation_id,
                content_markdown=crawl.content_markdown,
                content_html=crawl.content_html,
                structured_json=json.dumps(crawl.structured_json or {}),
                metadata_json=json.dumps(crawl.metadata_json or {}),
                links_json=json.dumps(crawl.links_json or {}),
                screenshots_paths_json=None,
                raw_response_json=json.dumps(crawl.raw_response_json or {}),
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

        if crawl.status != "ok" or not (has_markdown or has_html):
            await self._handle_crawl_error(
                message, req_id, crawl, correlation_id, interaction_id, has_markdown, has_html
            )
            raise ValueError("Firecrawl extraction failed")

        # Process successful crawl
        return await self._process_successful_crawl(message, crawl, correlation_id)

    async def _handle_crawl_error(
        self,
        message: Any,
        req_id: int,
        crawl: FirecrawlResult,
        correlation_id: str | None,
        interaction_id: int | None,
        has_markdown: bool,
        has_html: bool,
    ) -> None:
        """Handle Firecrawl extraction errors."""
        self.db.update_request_status(req_id, "error")
        await self.response_formatter.send_error_notification(
            message, "firecrawl_error", correlation_id
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

    async def _process_successful_crawl(
        self, message: Any, crawl: FirecrawlResult, correlation_id: str | None
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
                message, len(content_text)
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
                content_text = normalize_with_textacy(content_text)
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

            entities_json = json.dumps([_ent_to_dict(e) for e in entities_obj], ensure_ascii=False)
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
        media_file_ids_json = (
            json.dumps(valid_media_file_ids, ensure_ascii=False) if valid_media_file_ids else None
        )

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
                    raw_json = json.dumps(message_dict, ensure_ascii=False)
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


class MockCrawl:
    """Mock crawl object for reused content."""

    def __init__(self, markdown: str | None, html: str | None):
        self.status = "ok"
        self.http_status = 200
        self.content_markdown = markdown
        self.content_html = html
        self.structured_json = None
        self.metadata_json = None
        self.links_json = None
        self.raw_response_json = None
        self.latency_ms = None
        self.error_text = None
        self.source_url = None
        self.endpoint = "/v1/scrape"
        self.options_json = None
        self.correlation_id = None
