"""Tests for Twitter/X extraction orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.twitter.article_link_resolver import TwitterArticleLinkResolution
from app.adapters.twitter.graphql_parser import ExtractionResult, TweetData
from app.adapters.twitter.twitter_extractor import TwitterExtractor
from app.core.url_utils import compute_dedupe_hash


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


def _make_cfg(
    *,
    playwright_enabled: bool = False,
    prefer_firecrawl: bool = True,
    article_redirect_resolution_enabled: bool = True,
    force_tier: str = "auto",
    twitter_scraper_profile: str = "inherit",
    scraper_profile: str = "balanced",
) -> SimpleNamespace:
    return SimpleNamespace(
        scraper=SimpleNamespace(profile=scraper_profile),
        twitter=SimpleNamespace(
            cookies_path="/tmp/nonexistent-twitter-cookies.txt",
            prefer_firecrawl=prefer_firecrawl,
            playwright_enabled=playwright_enabled,
            force_tier=force_tier,
            scraper_profile=twitter_scraper_profile,
            max_concurrent_browsers=2,
            headless=True,
            page_timeout_ms=15000,
            article_redirect_resolution_enabled=article_redirect_resolution_enabled,
            article_resolution_timeout_sec=5.0,
        ),
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
async def test_extract_content_pure_requires_at_least_one_tier() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="unused", content_html=None)
    extractor = _make_extractor(
        cfg=_make_cfg(playwright_enabled=False, prefer_firecrawl=False),
        crawl_result=crawl_result,
    )

    with pytest.raises(ValueError, match="both Firecrawl and Playwright are disabled"):
        await extractor.extract_content_pure("https://x.com/user/status/1", correlation_id="cid")


@pytest.mark.asyncio
async def test_extract_content_pure_resolves_redirected_article_links() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)
    resolution = TwitterArticleLinkResolution(
        input_url="https://t.co/abc",
        resolved_url="https://x.com/i/article/42",
        canonical_url="https://x.com/i/article/42",
        article_id="42",
        is_article=True,
        reason="redirect_match",
    )

    with patch(
        "app.adapters.twitter.twitter_extractor.resolve_twitter_article_link",
        new=AsyncMock(return_value=resolution),
    ):
        with patch.object(
            extractor,
            "_pw_extract_article",
            new=AsyncMock(return_value=("Article body", "twitter_article", {"title": "T"})),
        ) as pw_extract_article:
            content_text, content_source, metadata = await extractor.extract_content_pure(
                "https://t.co/abc",
                correlation_id="cid",
            )

    assert content_text == "Article body"
    assert content_source == "twitter_article"
    assert metadata["is_article"] is True
    assert metadata["article_id"] == "42"
    assert metadata["article_resolution_reason"] == "redirect_match"
    assert metadata["article_canonical_url"] == "https://x.com/i/article/42"
    assert metadata["article_extraction_stage"] == "playwright"
    pw_extract_article.assert_awaited_once()
    assert pw_extract_article.await_args.kwargs["url"] == "https://x.com/i/article/42"


@pytest.mark.asyncio
async def test_extract_and_process_uses_canonical_article_for_dedupe() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=False), crawl_result=crawl_result)
    resolution = TwitterArticleLinkResolution(
        input_url="https://t.co/abc",
        resolved_url="https://x.com/i/article/777",
        canonical_url="https://x.com/i/article/777",
        article_id="777",
        is_article=True,
        reason="redirect_match",
    )
    expected_hash = compute_dedupe_hash("https://x.com/i/article/777")

    with patch(
        "app.adapters.twitter.twitter_extractor.resolve_twitter_article_link",
        new=AsyncMock(return_value=resolution),
    ):
        with patch.object(
            extractor,
            "_try_firecrawl",
            new=AsyncMock(return_value=(True, "Article text", "markdown")),
        ):
            req_id, *_rest = await extractor.extract_and_process(
                message=MagicMock(),
                url_text="https://t.co/abc",
                correlation_id="cid",
                interaction_id=None,
                silent=True,
            )

    assert req_id == 1
    handle_request_mock: Any = extractor._handle_request_dedupe_or_create
    handle_call = handle_request_mock.await_args
    assert handle_call.args[3] == expected_hash


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
async def test_force_tier_playwright_skips_firecrawl() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="unused", content_html=None)
    extractor = _make_extractor(
        cfg=_make_cfg(playwright_enabled=True, force_tier="playwright"),
        crawl_result=crawl_result,
    )

    with (
        patch.object(extractor, "_try_firecrawl", new=AsyncMock()) as mock_try_firecrawl,
        patch.object(
            extractor,
            "_extract_playwright",
            new=AsyncMock(return_value=("pw body", "twitter_graphql", {"source": "twitter"})),
        ) as mock_extract_playwright,
    ):
        content_text, content_source, _meta = await extractor.extract_content_pure(
            "https://x.com/user/status/1",
            correlation_id="cid",
        )

    assert content_text == "pw body"
    assert content_source == "twitter_graphql"
    mock_try_firecrawl.assert_not_awaited()
    mock_extract_playwright.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_tier_firecrawl_skips_playwright() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="yes", content_html=None)
    extractor = _make_extractor(
        cfg=_make_cfg(playwright_enabled=True, force_tier="firecrawl"),
        crawl_result=crawl_result,
    )

    with (
        patch.object(
            extractor,
            "_try_firecrawl",
            new=AsyncMock(return_value=(True, "firecrawl body", "markdown")),
        ) as mock_try_firecrawl,
        patch.object(extractor, "_extract_playwright", new=AsyncMock()) as mock_extract_playwright,
    ):
        content_text, content_source, _meta = await extractor.extract_content_pure(
            "https://x.com/user/status/1",
            correlation_id="cid",
        )

    assert content_text == "firecrawl body"
    assert content_source == "markdown"
    mock_try_firecrawl.assert_awaited_once()
    mock_extract_playwright.assert_not_awaited()


@pytest.mark.asyncio
async def test_twitter_profile_inherit_applies_timeout_multiplier() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(
        cfg=_make_cfg(
            playwright_enabled=True,
            force_tier="playwright",
            twitter_scraper_profile="inherit",
            scraper_profile="robust",
        ),
        crawl_result=crawl_result,
    )

    with patch.object(
        extractor,
        "_pw_extract_tweet",
        new=AsyncMock(return_value=("tweet", "twitter_graphql", {})),
    ) as mock_pw:
        await extractor._extract_playwright(
            "https://x.com/user/status/1",
            tweet_id="1",
            is_article=False,
            correlation_id="cid",
            metadata={},
            request_id=1,
        )

    assert mock_pw.await_args.kwargs["timeout_ms"] == 20250


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
async def test_expand_tco_urls_replaces_nested_quote_tweet_links() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    quoted = TweetData(
        tweet_id="2",
        author="B",
        author_handle="b",
        text="Quote https://t.co/quoted1",
        order=0,
    )
    tweets = [
        TweetData(
            tweet_id="1",
            author="A",
            author_handle="a",
            text="Main https://t.co/main1",
            quote_tweet=quoted,
            order=0,
        )
    ]

    async def _resolve(url: str) -> str | None:
        return {
            "https://t.co/main1": "https://example.com/main",
            "https://t.co/quoted1": "https://example.com/quote",
        }.get(url)

    with patch(
        "app.adapters.twitter.playwright_client.resolve_tco_url",
        new=AsyncMock(side_effect=_resolve),
    ):
        await extractor._expand_tco_urls_in_tweets(tweets, "cid")

    assert "https://example.com/main" in tweets[0].text
    assert "https://example.com/quote" in (
        tweets[0].quote_tweet.text if tweets[0].quote_tweet else ""
    )


@pytest.mark.asyncio
async def test_expand_tco_urls_caps_resolution_work() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    tweets = [
        TweetData(
            tweet_id=str(i),
            author="A",
            author_handle="a",
            text=f"Link https://t.co/id{i:02d}",
            order=i,
        )
        for i in range(25)
    ]

    resolver = AsyncMock(
        side_effect=lambda url: url.replace("https://t.co/", "https://resolved.example/")
    )
    with patch("app.adapters.twitter.playwright_client.resolve_tco_url", new=resolver):
        await extractor._expand_tco_urls_in_tweets(tweets, "cid")

    # Expansion is capped to protect latency and network usage.
    assert resolver.await_count == 20
    assert "https://resolved.example/id00" in tweets[0].text
    assert "https://t.co/id24" in tweets[24].text


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


@pytest.mark.asyncio
async def test_pw_extract_article_returns_resolved_and_canonical_metadata() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    article_data = {
        "title": "X",
        "author": "",
        "content": "My title\nAuthor Name\n@author\nBody paragraph one.\nBody paragraph two.",
        "finalUrl": "https://x.com/i/article/42",
        "canonicalUrl": "https://x.com/i/article/42",
        "selectorFallbackUsed": True,
        "contentSelector": "main",
    }
    with patch(
        "app.adapters.twitter.playwright_client.scrape_article",
        new=AsyncMock(return_value=article_data),
    ):
        content_text, source, metadata = await extractor._pw_extract_article(
            url="https://x.com/i/article/42",
            cookies=None,
            headless=True,
            timeout_ms=30000,
            correlation_id="cid",
        )

    assert source == "twitter_article"
    assert content_text
    assert metadata["article_resolved_url"] == "https://x.com/i/article/42"
    assert metadata["article_canonical_url"] == "https://x.com/i/article/42"
    assert metadata["article_id"] == "42"


@pytest.mark.asyncio
async def test_pw_extract_article_rejects_empty_content_with_reason() -> None:
    crawl_result = SimpleNamespace(status="error", content_markdown=None, content_html=None)
    extractor = _make_extractor(cfg=_make_cfg(playwright_enabled=True), crawl_result=crawl_result)

    with patch(
        "app.adapters.twitter.playwright_client.scrape_article",
        new=AsyncMock(return_value={"title": "X", "author": "", "content": "   "}),
    ):
        with pytest.raises(ValueError, match="reason=empty_content"):
            await extractor._pw_extract_article(
                url="https://x.com/i/article/1",
                cookies=None,
                headless=True,
                timeout_ms=30000,
                correlation_id="cid",
            )


def test_detect_article_redirect_single_url() -> None:
    """Tweet with only an article URL should be detected as redirect."""
    tweets = [
        TweetData(
            tweet_id="1",
            author="A",
            author_handle="a",
            text="https://x.com/i/article/12345",
            order=0,
        )
    ]
    result = TwitterExtractor._detect_article_redirect(tweets)
    assert result == "https://x.com/i/article/12345"


def test_detect_article_redirect_non_article_url() -> None:
    """Tweet with a non-article URL should not trigger redirect."""
    tweets = [
        TweetData(
            tweet_id="1",
            author="A",
            author_handle="a",
            text="https://example.com/article",
            order=0,
        )
    ]
    assert TwitterExtractor._detect_article_redirect(tweets) is None


def test_detect_article_redirect_text_with_url() -> None:
    """Tweet with text + URL should not trigger redirect."""
    tweets = [
        TweetData(
            tweet_id="1",
            author="A",
            author_handle="a",
            text="Check out https://x.com/i/article/12345",
            order=0,
        )
    ]
    assert TwitterExtractor._detect_article_redirect(tweets) is None


def test_detect_article_redirect_empty() -> None:
    assert TwitterExtractor._detect_article_redirect([]) is None
