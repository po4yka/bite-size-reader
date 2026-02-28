"""Tests for Twitter routing in message-independent content extraction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.content.content_extractor import ContentExtractor

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
                headless=True,
                page_timeout_ms=15000,
                cookies_path="/tmp/nonexistent-twitter-cookies.txt",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_extract_content_pure_routes_twitter_urls_to_twitter_extractor() -> None:
    firecrawl_scrape_mock = AsyncMock()
    firecrawl = cast("FirecrawlClient", SimpleNamespace(scrape_markdown=firecrawl_scrape_mock))
    extractor = ContentExtractor(
        cfg=_dummy_cfg(),
        db=cast("DatabaseSessionManager", SimpleNamespace()),
        firecrawl=firecrawl,
        response_formatter=cast("ResponseFormatter", SimpleNamespace()),
        audit_func=lambda *args, **kwargs: None,
        sem=_dummy_sem,
    )
    extract_twitter_mock: AsyncMock = AsyncMock(
        return_value=("tweet text", "twitter_graphql", {"source": "twitter"})
    )
    with patch.object(extractor, "_extract_twitter_content_pure", new=extract_twitter_mock):
        content_text, content_source, metadata = await extractor.extract_content_pure(
            "https://x.com/user/status/123?s=20&t=abc",
            correlation_id="cid",
        )

    assert content_text == "tweet text"
    assert content_source == "twitter_graphql"
    assert metadata["source"] == "twitter"
    extract_twitter_mock.assert_awaited_once_with(
        "https://x.com/user/status/123?s=20&t=abc",
        "cid",
    )
    assert firecrawl_scrape_mock.await_count == 0
