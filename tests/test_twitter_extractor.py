"""Tests for Twitter/X extraction orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.twitter.graphql_parser import ExtractionResult, TweetData
from app.adapters.twitter.twitter_extractor import TwitterExtractor


class _DummySemCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> bool:
        return False


def _make_cfg(*, playwright_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        twitter=SimpleNamespace(
            cookies_path="/tmp/nonexistent-twitter-cookies.txt",
            prefer_firecrawl=True,
            playwright_enabled=playwright_enabled,
            headless=True,
            page_timeout_ms=15000,
        )
    )


def _make_extractor(*, cfg: Any, crawl_result: Any) -> TwitterExtractor:
    firecrawl: Any = SimpleNamespace(scrape_markdown=AsyncMock(return_value=crawl_result))
    message_persistence: Any = SimpleNamespace(
        request_repo=SimpleNamespace(
            async_update_request_status=AsyncMock(),
            async_update_request_lang_detected=AsyncMock(),
        )
    )
    response_formatter: Any = SimpleNamespace(
        send_url_accepted_notification=AsyncMock(),
        send_error_notification=AsyncMock(),
    )
    return TwitterExtractor(
        cfg=cfg,
        db=MagicMock(),
        firecrawl=firecrawl,
        response_formatter=response_formatter,
        message_persistence=message_persistence,
        firecrawl_sem=lambda: _DummySemCtx(),
        handle_request_dedupe_or_create=AsyncMock(return_value=1),
        schedule_crawl_persistence=MagicMock(),
    )


@pytest.mark.asyncio
async def test_try_firecrawl_accepts_short_tweet_content() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="Yes", content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(), crawl_result=crawl_result)

    ok, content_text, content_source = await extractor._try_firecrawl(
        "https://x.com/user/status/1",
        1,
        "1",
        {},
        "cid",
        False,
    )

    assert ok is True
    assert content_source == "markdown"
    assert "Yes" in content_text


@pytest.mark.asyncio
async def test_try_firecrawl_keeps_article_quality_gate() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="Yes", content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(), crawl_result=crawl_result)

    ok, content_text, content_source = await extractor._try_firecrawl(
        "https://x.com/i/article/1",
        1,
        None,
        {},
        "cid",
        True,
    )

    assert ok is False
    assert content_text == ""
    assert content_source == "none"


@pytest.mark.asyncio
async def test_pw_extract_tweet_requires_requested_tweet_id() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    result = ExtractionResult(
        url="https://x.com/user/status/999",
        tweets=[TweetData(tweet_id="123", author="A", author_handle="a", text="text", order=0)],
    )
    with patch(
        "app.adapters.twitter.playwright_client.extract_tweet",
        new=AsyncMock(return_value=result),
    ):
        with pytest.raises(ValueError, match="did not include requested tweet_id=999"):
            await extractor._pw_extract_tweet(
                url="https://x.com/user/status/999",
                tweet_id="999",
                cookies=Path("/tmp/none"),
                headless=True,
                timeout_ms=1000,
                correlation_id="cid",
            )


@pytest.mark.asyncio
async def test_pw_extract_tweet_expands_tco_urls() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    result = ExtractionResult(
        url="https://x.com/user/status/123",
        tweets=[
            TweetData(
                tweet_id="123",
                author="A",
                author_handle="a",
                text="Read this https://t.co/abc123",
                order=0,
            )
        ],
    )
    with patch(
        "app.adapters.twitter.playwright_client.extract_tweet",
        new=AsyncMock(return_value=result),
    ):
        with patch(
            "app.adapters.twitter.playwright_client.resolve_tco_url",
            new=AsyncMock(return_value="https://example.com/article"),
        ):
            content_text, _source, _meta = await extractor._pw_extract_tweet(
                url="https://x.com/user/status/123",
                tweet_id="123",
                cookies=None,
                headless=True,
                timeout_ms=1000,
                correlation_id="cid",
            )

    assert "https://example.com/article" in content_text
    assert "https://t.co/abc123" not in content_text


@pytest.mark.asyncio
async def test_pw_extract_article_rejects_login_wall_content() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    article_data = {
        "title": "X",
        "author": "",
        "content": "Log in to X to continue reading. By signing up, you agree to Terms of Service.",
    }
    with patch(
        "app.adapters.twitter.playwright_client.scrape_article",
        new=AsyncMock(return_value=article_data),
    ):
        with pytest.raises(ValueError, match="UI/login content"):
            await extractor._pw_extract_article(
                url="https://x.com/i/article/1",
                cookies=None,
                headless=True,
                timeout_ms=30000,
                correlation_id="cid",
            )
