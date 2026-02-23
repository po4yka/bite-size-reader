"""Content extraction and processing for URLs."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.content.content_extractor_crawl import ContentExtractorCrawlMixin
from app.adapters.content.content_extractor_platforms import ContentExtractorPlatformsMixin
from app.adapters.content.content_extractor_requests import ContentExtractorRequestsMixin
from app.adapters.content.quality_filters import detect_low_value_content
from app.adapters.external.firecrawl_parser import FirecrawlClient, FirecrawlResult
from app.config import AppConfig
from app.core.html_utils import clean_markdown_article_text, html_to_text
from app.core.lang import detect_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.session import DatabaseSessionManager
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.persistence.message_persistence import MessagePersistence

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.youtube.youtube_downloader import YouTubeDownloader
    from app.core.progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)

# Route versioning constants
URL_ROUTE_VERSION = 1


class ContentExtractor(
    ContentExtractorRequestsMixin,
    ContentExtractorCrawlMixin,
    ContentExtractorPlatformsMixin,
):
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
        self._youtube_downloader: YouTubeDownloader | None = None
        self._twitter_extractor: Any | None = None

    async def extract_content_pure(
        self,
        url: str,
        correlation_id: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Pure extraction method without message dependencies."""
        normalized_url = normalize_url(url)

        logger.info(
            "pure_extraction_start",
            extra={"url": url, "normalized": normalized_url, "cid": correlation_id},
        )

        async with self._sem():
            crawl = await self.firecrawl.scrape_markdown(url, request_id=None)

        quality_issue = detect_low_value_content(crawl)
        if quality_issue:
            reason = quality_issue["reason"]
            logger.warning(
                "pure_extraction_low_value", extra={"cid": correlation_id, "reason": reason}
            )
            raise ValueError(f"Low-value content detected: {reason}")

        has_markdown = bool(crawl.content_markdown and crawl.content_markdown.strip())
        has_html = bool(crawl.content_html and crawl.content_html.strip())

        if crawl.status != "ok" or not (has_markdown or has_html):
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
            except Exception:
                pass

            error_msg = crawl.error_text or "Firecrawl extraction failed"
            raise ValueError(f"Extraction failed: {error_msg}") from None

        if crawl.content_markdown and crawl.content_markdown.strip():
            content_text = clean_markdown_article_text(crawl.content_markdown)
            content_source = "markdown"
        elif crawl.content_html and crawl.content_html.strip():
            content_text = html_to_text(crawl.content_html)
            content_source = "html"
        else:
            content_text = ""
            content_source = "none"

        metadata = {
            "extraction_method": "firecrawl",
            "http_status": crawl.http_status,
            "endpoint": crawl.endpoint,
            "latency_ms": crawl.latency_ms,
            "content_length": len(content_text),
            "source_format": content_source,
        }

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
        progress_tracker: ProgressTracker | None = None,
    ) -> tuple[int, str, str, str, str | None, list[str]]:
        """Extract content from URL and return request/content metadata tuple."""
        from app.core.url_utils import is_twitter_url, is_youtube_url

        norm = normalize_url(url_text)

        if is_twitter_url(norm) and self.cfg.twitter.enabled:
            logger.info("twitter_url_detected", extra={"url": url_text, "cid": correlation_id})
            (
                req_id,
                content_text,
                content_source,
                detected_lang,
                meta,
            ) = await self._extract_twitter_content(
                message, url_text, norm, correlation_id, interaction_id, silent
            )
            title = meta.get("title") if isinstance(meta, dict) else None
            return req_id, content_text, content_source, detected_lang, title, []

        if is_youtube_url(norm):
            logger.info(
                "youtube_url_detected",
                extra={"url": url_text, "normalized": norm, "cid": correlation_id},
            )
            (
                req_id,
                transcript_text,
                content_source,
                detected_lang,
                video_metadata,
            ) = await self._extract_youtube_content(
                message, url_text, norm, correlation_id, interaction_id, silent, progress_tracker
            )
            title = video_metadata.get("title") if isinstance(video_metadata, dict) else None
            return req_id, transcript_text, content_source, detected_lang, title, []

        dedupe = url_hash_sha256(norm)
        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm, "hash": dedupe, "cid": correlation_id},
        )
        await self.response_formatter.send_url_accepted_notification(
            message, norm, correlation_id, silent=silent
        )
        req_id = await self._handle_request_dedupe_or_create(
            message, url_text, norm, dedupe, correlation_id
        )
        (
            content_text,
            content_source,
            title,
            images,
        ) = await self._extract_or_reuse_content_with_title(
            message, req_id, url_text, dedupe, correlation_id, interaction_id, silent=silent
        )
        detected = detect_language(content_text or "")
        try:
            await self.message_persistence.request_repo.async_update_request_lang_detected(
                req_id, detected
            )
        except Exception as e:
            logger.error(
                "persist_lang_detected_error", extra={"error": str(e), "cid": correlation_id}
            )
        return req_id, content_text, content_source, detected, title, images
