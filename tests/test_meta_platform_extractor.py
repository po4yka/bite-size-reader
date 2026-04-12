from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.platform_extraction.models import PlatformExtractionRequest
from app.adapters.meta.platform_extractor import MetaPlatformExtractor
from app.domain.models.source import SourceKind


class _DummySemCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self, exc_type: object | None, exc: BaseException | None, tb: object | None
    ) -> bool:
        return False


def _make_lifecycle() -> Any:
    lifecycle = MagicMock()
    lifecycle.send_accepted_notification = AsyncMock()
    lifecycle.handle_request_dedupe_or_create = AsyncMock(return_value=41)
    lifecycle.persist_detected_lang = AsyncMock()
    return lifecycle


def _make_extractor(*, crawl_result: Any) -> tuple[MetaPlatformExtractor, Any]:
    scraper = SimpleNamespace(scrape_markdown=AsyncMock(return_value=crawl_result))
    lifecycle = _make_lifecycle()
    extractor = MetaPlatformExtractor(
        scraper=scraper,
        firecrawl_sem=lambda: _DummySemCtx(),
        lifecycle=lifecycle,
    )
    return extractor, lifecycle


def _make_request(url: str, *, mode: str = "pure") -> PlatformExtractionRequest:
    return PlatformExtractionRequest(
        message=MagicMock() if mode == "interactive" else None,
        url_text=url,
        normalized_url=url,
        correlation_id="cid",
        silent=True,
        request_id_override=77 if mode == "pure" else None,
        mode=mode,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_threads_extractor_preserves_quote_and_media_metadata() -> None:
    crawl_result = SimpleNamespace(
        status="ok",
        content_markdown="Main Threads body",
        content_html=None,
        metadata_json={
            "title": "Threads title",
            "quoted_post": {"author": "quoted_user", "text": "Quoted post body"},
            "media": [
                {"type": "image", "url": "https://cdn.example.com/thread-image.jpg"},
                {"type": "video", "url": "https://cdn.example.com/thread-video.mp4"},
            ],
        },
    )
    extractor, _ = _make_extractor(crawl_result=crawl_result)

    result = await extractor.extract(_make_request("https://www.threads.net/@user/post/C8abc123"))

    assert result.source_item is not None
    assert result.source_item.kind == SourceKind.THREADS_POST
    assert result.source_item.external_id == "C8abc123"
    assert result.content_source == "markdown"
    assert result.normalized_document is not None
    assert result.normalized_document.source_kind == SourceKind.THREADS_POST
    assert len(result.normalized_document.media) == 2
    assert {asset.kind.value for asset in result.normalized_document.media} == {"image", "video"}
    assert any(
        block.metadata.get("role") == "quoted_context"
        for block in result.normalized_document.text_blocks
    )


@pytest.mark.asyncio
async def test_instagram_post_upgrades_to_carousel_when_multiple_images_exist() -> None:
    crawl_result = SimpleNamespace(
        status="ok",
        content_markdown="Carousel caption",
        content_html=None,
        metadata_json={
            "title": "Carousel title",
            "images": [
                "https://cdn.example.com/slide-1.jpg",
                "https://cdn.example.com/slide-2.jpg",
            ],
        },
    )
    extractor, _ = _make_extractor(crawl_result=crawl_result)

    result = await extractor.extract(_make_request("https://www.instagram.com/p/DApost123/"))

    assert result.source_item is not None
    assert result.source_item.kind == SourceKind.INSTAGRAM_CAROUSEL
    assert result.normalized_document is not None
    assert result.normalized_document.source_kind == SourceKind.INSTAGRAM_CAROUSEL
    assert len(result.images) == 2


@pytest.mark.asyncio
async def test_instagram_reel_uses_metadata_fallback_for_login_wall_content() -> None:
    crawl_result = SimpleNamespace(
        status="ok",
        content_markdown="Log in to see Instagram photos and videos from friends you know.",
        content_html=None,
        metadata_json={
            "title": "Reel title",
            "description": "Reel caption text",
            "video_url": "https://cdn.example.com/reel.mp4",
            "audio_transcript": "Transcript fallback",
            "ocr_text": "Frame OCR fallback",
        },
    )
    extractor, lifecycle = _make_extractor(crawl_result=crawl_result)

    result = await extractor.extract(
        _make_request("https://www.instagram.com/reel/DAreel456/", mode="interactive")
    )

    assert result.source_item is not None
    assert result.source_item.kind == SourceKind.INSTAGRAM_REEL
    assert result.content_source == "meta_metadata_fallback"
    assert "Reel caption text" in result.content_text
    assert "Transcript fallback" in result.content_text
    assert result.normalized_document is not None
    assert {block.kind.value for block in result.normalized_document.text_blocks} >= {
        "body",
        "transcript",
        "ocr",
    }
    assert result.metadata["video_provenance"]["primary_fact_source"] == "transcript"
    assert result.metadata["video_provenance"]["transcript_source"] == "audio_transcript"
    assert result.metadata["video_controls"]["audio_transcription_enabled"] is True
    lifecycle.handle_request_dedupe_or_create.assert_awaited_once()
    lifecycle.persist_detected_lang.assert_awaited_once()
