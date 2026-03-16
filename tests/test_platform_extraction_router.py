from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.platform_extraction.models import PlatformExtractionResult

if TYPE_CHECKING:
    from app.adapters.external.firecrawl_parser import FirecrawlClient
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


@asynccontextmanager
async def _dummy_sem():
    yield


def _dummy_cfg() -> AppConfig:
    return cast(
        "AppConfig",
        SimpleNamespace(
            runtime=SimpleNamespace(enable_textacy=False, request_timeout_sec=5),
            scraper=SimpleNamespace(profile="balanced"),
            redis=SimpleNamespace(
                enabled=False,
                cache_enabled=False,
                prefix="test",
                required=False,
                cache_timeout_sec=0.1,
                firecrawl_ttl_seconds=0,
            ),
            twitter=SimpleNamespace(
                enabled=True,
                prefer_firecrawl=True,
                playwright_enabled=False,
                force_tier="auto",
                scraper_profile="inherit",
                max_concurrent_browsers=2,
                headless=True,
                page_timeout_ms=15000,
                cookies_path="/tmp/nonexistent-twitter-cookies.txt",
                article_redirect_resolution_enabled=True,
                article_resolution_timeout_sec=5.0,
            ),
            youtube=SimpleNamespace(enabled=True),
        ),
    )


def _make_extractor() -> ContentExtractor:
    firecrawl_scrape_mock = AsyncMock(
        return_value=SimpleNamespace(
            status="ok",
            content_markdown="# Title\n\nBody",
            content_html=None,
            error_text=None,
            http_status=200,
            latency_ms=1,
            endpoint="scraper",
            metadata_json=None,
            response_success=True,
            source_url="https://example.com",
            correlation_id="cid",
            options_json=None,
        )
    )
    firecrawl = cast("FirecrawlClient", SimpleNamespace(scrape_markdown=firecrawl_scrape_mock))
    return ContentExtractor(
        cfg=_dummy_cfg(),
        db=cast("DatabaseSessionManager", SimpleNamespace()),
        firecrawl=firecrawl,  # type: ignore[arg-type]
        response_formatter=cast(
            "ResponseFormatter", SimpleNamespace(send_url_accepted_notification=AsyncMock())
        ),
        audit_func=lambda *args, **kwargs: None,
        sem=_dummy_sem,
    )


@pytest.mark.asyncio
async def test_extract_content_pure_routes_youtube_urls_through_platform_router() -> None:
    extractor = _make_extractor()
    router = MagicMock()
    router.extract = AsyncMock(
        return_value=PlatformExtractionResult(
            platform="youtube",
            request_id=42,
            content_text="transcript text",
            content_source="youtube-transcript-api",
            detected_lang="en",
            title="Video",
            metadata={"source": "youtube"},
        )
    )
    extractor._platform_router = router

    content_text, content_source, metadata = await extractor.extract_content_pure(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        correlation_id="cid",
        request_id=42,
    )

    assert content_text == "transcript text"
    assert content_source == "youtube-transcript-api"
    assert metadata["source"] == "youtube"
    assert metadata["request_id"] == 42
    router.extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_content_pure_routes_twitter_urls_through_platform_router() -> None:
    extractor = _make_extractor()
    router = MagicMock()
    router.extract = AsyncMock(
        return_value=PlatformExtractionResult(
            platform="twitter",
            request_id=None,
            content_text="tweet text",
            content_source="twitter_graphql",
            detected_lang="en",
            title=None,
            metadata={"source": "twitter"},
        )
    )
    extractor._platform_router = router

    content_text, content_source, metadata = await extractor.extract_content_pure(
        "https://x.com/user/status/123?s=20&t=abc",
        correlation_id="cid",
    )

    assert content_text == "tweet text"
    assert content_source == "twitter_graphql"
    assert metadata["source"] == "twitter"
    router.extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_and_process_content_routes_platform_urls_before_generic_scrape() -> None:
    extractor = _make_extractor()
    router = MagicMock()
    router.extract = AsyncMock(
        return_value=PlatformExtractionResult(
            platform="twitter",
            request_id=9,
            content_text="tweet text",
            content_source="twitter_graphql",
            detected_lang="en",
            title="Title",
            images=[],
            metadata={"source": "twitter"},
        )
    )
    extractor._platform_router = router

    result = await extractor.extract_and_process_content(
        message=MagicMock(),
        url_text="https://x.com/user/status/123",
        correlation_id="cid",
        interaction_id=None,
        silent=True,
    )

    assert result == (9, "tweet text", "twitter_graphql", "en", "Title", [])
    extractor.firecrawl.scrape_markdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_urls_fall_back_to_existing_scraper_chain_when_router_misses() -> None:
    extractor: Any = _make_extractor()
    router = MagicMock()
    router.extract = AsyncMock(return_value=None)
    extractor._platform_router = router
    extractor._handle_request_dedupe_or_create = AsyncMock(return_value=55)
    extractor._extract_or_reuse_content_with_title = AsyncMock(
        return_value=("body", "markdown", "Title", [])
    )

    result = await extractor.extract_and_process_content(
        message=MagicMock(),
        url_text="https://example.com/article",
        correlation_id="cid",
        interaction_id=None,
        silent=True,
    )

    assert result == (55, "body", "markdown", "en", "Title", [])
    extractor._handle_request_dedupe_or_create.assert_awaited_once()
