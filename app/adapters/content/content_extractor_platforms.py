"""Platform-specific extraction routes for content extractor."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from app.core.progress_tracker import ProgressTracker

logger = logging.getLogger("app.adapters.content.content_extractor")


class ContentExtractorPlatformsMixin:
    """YouTube and Twitter/X extraction paths."""

    _youtube_downloader: Any | None
    _twitter_extractor: Any | None

    async def _extract_youtube_content(
        self,
        message: Any,
        url_text: str,
        norm: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
        progress_tracker: ProgressTracker | None = None,
    ) -> tuple[int, str, str, str, dict[str, Any]]:
        """Extract YouTube video transcript and download video."""
        if not self.cfg.youtube.enabled:
            logger.warning(
                "youtube_download_disabled",
                extra={"url": url_text, "cid": correlation_id},
            )
            raise ValueError("YouTube video download is disabled in configuration")

        if self._youtube_downloader is None:
            from app.adapters.youtube.youtube_downloader import YouTubeDownloader

            self._youtube_downloader = YouTubeDownloader(
                cfg=self.cfg,
                db=self.db,
                response_formatter=self.response_formatter,
                audit_func=self._audit,
            )

        try:
            (
                req_id,
                transcript_text,
                content_source,
                detected_lang,
                video_metadata,
            ) = await self._youtube_downloader.download_and_extract(
                message, url_text, correlation_id, interaction_id, silent, progress_tracker
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

            return req_id, transcript_text, content_source, detected_lang, video_metadata

        except Exception as e:
            raise_if_cancelled(e)
            logger.exception(
                "youtube_extraction_failed",
                extra={"url": url_text, "error": str(e), "cid": correlation_id},
            )
            raise

    async def _extract_twitter_content(
        self,
        message: Any,
        url_text: str,
        norm: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[int, str, str, str, dict[str, Any]]:
        """Extract Twitter/X content via TwitterExtractor (two-tier strategy)."""
        if self._twitter_extractor is None:
            from app.adapters.twitter.twitter_extractor import TwitterExtractor

            self._twitter_extractor = TwitterExtractor(
                cfg=self.cfg,
                db=self.db,
                firecrawl=self.firecrawl,
                response_formatter=self.response_formatter,
                message_persistence=self.message_persistence,
                firecrawl_sem=self._sem,
                handle_request_dedupe_or_create=self._handle_request_dedupe_or_create,
                schedule_crawl_persistence=self._schedule_crawl_persistence,
            )
        return await self._twitter_extractor.extract_and_process(
            message, url_text, correlation_id, interaction_id, silent
        )
