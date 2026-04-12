from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.platform_extraction.models import PlatformExtractionRequest
from app.adapters.twitter.article_link_resolver import TwitterArticleLinkResolution
from app.adapters.twitter.firecrawl_extractor import TwitterFirecrawlExtractor
from app.adapters.twitter.graphql_parser import ExtractionResult, TweetData
from app.adapters.twitter.platform_extractor import TwitterPlatformExtractor
from app.adapters.twitter.playwright_extractor import TwitterPlaywrightExtractor
from app.core.url_utils import compute_dedupe_hash


class _DummySemCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self, exc_type: object | None, exc: BaseException | None, tb: object | None
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
) -> Any:
    return SimpleNamespace(
        scraper=SimpleNamespace(profile=scraper_profile),
        twitter=SimpleNamespace(
            enabled=True,
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


def _make_lifecycle() -> Any:
    lifecycle = MagicMock()
    lifecycle.send_accepted_notification = AsyncMock()
    lifecycle.handle_request_dedupe_or_create = AsyncMock(return_value=1)
    lifecycle.persist_detected_lang = AsyncMock()
    return lifecycle


def _make_platform_extractor(*, cfg: Any, crawl_result: Any) -> TwitterPlatformExtractor:
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
    return TwitterPlatformExtractor(
        cfg=cfg,
        db=MagicMock(),
        firecrawl=firecrawl,
        response_formatter=response_formatter,
        message_persistence=message_persistence,
        firecrawl_sem=lambda: _DummySemCtx(),
        schedule_crawl_persistence=MagicMock(),
        lifecycle=_make_lifecycle(),
    )


def _make_request(
    *, url_text: str, mode: str = "pure", silent: bool = True
) -> PlatformExtractionRequest:
    return PlatformExtractionRequest(
        message=MagicMock() if mode == "interactive" else None,
        url_text=url_text,
        normalized_url=url_text,
        correlation_id="cid",
        interaction_id=None,
        silent=silent,
        progress_tracker=None,
        request_id_override=99 if mode == "pure" else None,
        mode=mode,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_platform_extractor_requires_at_least_one_tier() -> None:
    extractor = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=False, prefer_firecrawl=False),
        crawl_result=SimpleNamespace(status="ok", content_markdown="unused", content_html=None),
    )

    with pytest.raises(ValueError, match="both Firecrawl and Playwright are disabled"):
        await extractor.extract(_make_request(url_text="https://x.com/user/status/1"))


@pytest.mark.asyncio
async def test_interactive_extract_uses_canonical_article_for_dedupe() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=False),
        crawl_result=SimpleNamespace(status="error", content_markdown=None, content_html=None),
    )
    coordinator: Any = extractor._coordinator
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
        "app.adapters.twitter.extraction_coordinator.resolve_twitter_article_link",
        new=AsyncMock(return_value=resolution),
    ):
        coordinator._firecrawl_extractor.extract = AsyncMock(
            return_value=(True, "Article text", "markdown")
        )
        await extractor.extract(_make_request(url_text="https://t.co/abc", mode="interactive"))

    coordinator._lifecycle.handle_request_dedupe_or_create.assert_awaited_once()
    assert (
        coordinator._lifecycle.handle_request_dedupe_or_create.await_args.kwargs["dedupe_hash"]
        == expected_hash
    )


@pytest.mark.asyncio
async def test_force_tier_playwright_skips_firecrawl() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=True, force_tier="playwright"),
        crawl_result=SimpleNamespace(status="ok", content_markdown="unused", content_html=None),
    )
    coordinator: Any = extractor._coordinator
    coordinator._firecrawl_extractor.extract = AsyncMock()
    coordinator._playwright_extractor.extract = AsyncMock(
        return_value=("pw body", "twitter_graphql", {"source": "twitter"})
    )

    result = await extractor.extract(_make_request(url_text="https://x.com/user/status/1"))

    assert result.content_text == "pw body"
    coordinator._firecrawl_extractor.extract.assert_not_awaited()
    coordinator._playwright_extractor.extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_tier_firecrawl_skips_playwright() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=True, force_tier="firecrawl"),
        crawl_result=SimpleNamespace(status="ok", content_markdown="yes", content_html=None),
    )
    coordinator: Any = extractor._coordinator
    coordinator._firecrawl_extractor.extract = AsyncMock(
        return_value=(True, "firecrawl body", "markdown")
    )
    coordinator._playwright_extractor.extract = AsyncMock()

    result = await extractor.extract(_make_request(url_text="https://x.com/user/status/1"))

    assert result.content_text == "firecrawl body"
    coordinator._firecrawl_extractor.extract.assert_awaited_once()
    coordinator._playwright_extractor.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_mode_runs_playwright_after_firecrawl_to_enrich_tweet_media() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=True, prefer_firecrawl=True),
        crawl_result=SimpleNamespace(status="ok", content_markdown="unused", content_html=None),
    )
    coordinator: Any = extractor._coordinator
    coordinator._firecrawl_extractor.extract = AsyncMock(
        return_value=(True, "firecrawl body", "markdown")
    )
    coordinator._playwright_extractor.extract = AsyncMock(
        return_value=(
            "playwright body",
            "twitter_graphql",
            {
                "tweet_media": [
                    {
                        "url": "https://pbs.twimg.com/media/chart.jpg",
                        "alt_text": "Revenue chart",
                        "tweet_id": "1",
                        "tweet_order": 0,
                    }
                ]
            },
        )
    )

    result = await extractor.extract(_make_request(url_text="https://x.com/user/status/1"))

    assert result.content_text == "playwright body"
    assert result.images == ["https://pbs.twimg.com/media/chart.jpg"]
    assert result.normalized_document is not None
    assert result.normalized_document.media[0].alt_text == "Revenue chart"
    coordinator._firecrawl_extractor.extract.assert_awaited_once()
    coordinator._playwright_extractor.extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_firecrawl_accepts_short_tweet_content() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="Yes", content_html=None)
    request_repo = SimpleNamespace()
    extractor = TwitterFirecrawlExtractor(
        firecrawl=SimpleNamespace(scrape_markdown=AsyncMock(return_value=crawl_result)),
        firecrawl_sem=lambda: _DummySemCtx(),
        schedule_crawl_persistence=MagicMock(),
        request_repo=request_repo,
    )

    ok, content_text, content_source = await extractor.extract(
        url_text="https://x.com/user/status/1",
        req_id=1,
        tweet_id="1",
        metadata={},
        correlation_id="cid",
        is_article=False,
        persist_result=False,
    )

    assert ok is True
    assert content_source == "markdown"
    assert "Yes" in content_text


@pytest.mark.asyncio
async def test_firecrawl_rejects_low_quality_article_content() -> None:
    crawl_result = SimpleNamespace(status="ok", content_markdown="Yes", content_html=None)
    request_repo = SimpleNamespace()
    extractor = TwitterFirecrawlExtractor(
        firecrawl=SimpleNamespace(scrape_markdown=AsyncMock(return_value=crawl_result)),
        firecrawl_sem=lambda: _DummySemCtx(),
        schedule_crawl_persistence=MagicMock(),
        request_repo=request_repo,
    )

    ok, content_text, content_source = await extractor.extract(
        url_text="https://x.com/i/article/1",
        req_id=1,
        tweet_id=None,
        metadata={},
        correlation_id="cid",
        is_article=True,
        persist_result=False,
    )

    assert ok is False
    assert content_text == ""
    assert content_source == "none"


@pytest.mark.asyncio
async def test_playwright_extracts_tweet_thread() -> None:
    extractor = TwitterPlaywrightExtractor(
        cfg=_make_cfg(playwright_enabled=True), request_repo=MagicMock()
    )
    result = ExtractionResult(
        url="https://x.com/user/status/1",
        tweets=[
            TweetData(
                tweet_id="1",
                author="User",
                order=0,
                text="hello world",
                author_handle="user",
                images=["https://pbs.twimg.com/media/chart.jpg"],
                alt_texts=["Revenue chart"],
            ),
            TweetData(
                tweet_id="2",
                author="User",
                order=1,
                text="reply",
                author_handle="user",
            ),
        ],
    )

    with patch(
        "app.adapters.twitter.playwright_extractor.extract_tweet",
        new=AsyncMock(return_value=result),
    ):
        content_text, content_source, metadata = await extractor.extract(
            url_text="https://x.com/user/status/1",
            tweet_id="1",
            is_article=False,
            correlation_id="cid",
            metadata={},
            timeout_ms=15000,
        )

    assert content_source == "twitter_graphql"
    assert metadata["tweet_count"] == 2
    assert metadata["tweet_media"][0]["url"] == "https://pbs.twimg.com/media/chart.jpg"
    assert metadata["tweet_media"][0]["alt_text"] == "Revenue chart"
    assert "hello world" in content_text


@pytest.mark.asyncio
async def test_playwright_extracts_article() -> None:
    extractor = TwitterPlaywrightExtractor(
        cfg=_make_cfg(playwright_enabled=True), request_repo=MagicMock()
    )

    with (
        patch(
            "app.adapters.twitter.playwright_extractor.scrape_article",
            new=AsyncMock(
                return_value={
                    "title": "Article title",
                    "author": "Author",
                    "authorHandle": "author",
                    "content": "Body text",
                    "images": [
                        "https://cdn.example.com/hero.jpg",
                        "https://cdn.example.com/logo.svg",
                    ],
                    "finalUrl": "https://x.com/i/article/42",
                    "canonicalUrl": "https://x.com/i/article/42",
                }
            ),
        ),
        patch(
            "app.adapters.twitter.playwright_extractor.is_low_quality_article_content",
            return_value=False,
        ),
    ):
        content_text, content_source, metadata = await extractor.extract(
            url_text="https://x.com/i/article/42",
            tweet_id=None,
            is_article=True,
            correlation_id="cid",
            metadata={},
            timeout_ms=15000,
            request_id=1,
        )

    assert content_source == "twitter_article"
    assert metadata["title"] == "Article title"
    assert metadata["article_images"] == ["https://cdn.example.com/hero.jpg"]
    assert "Body text" in content_text


@pytest.mark.asyncio
async def test_playwright_includes_quoted_post_media_in_same_source_item() -> None:
    extractor = TwitterPlaywrightExtractor(
        cfg=_make_cfg(playwright_enabled=True), request_repo=MagicMock()
    )
    result = ExtractionResult(
        url="https://x.com/user/status/1",
        tweets=[
            TweetData(
                tweet_id="1",
                author="User",
                order=0,
                text="commentary",
                author_handle="user",
                quote_tweet=TweetData(
                    tweet_id="9",
                    author="Quoted",
                    order=0,
                    text="quoted body",
                    author_handle="quoted",
                    images=["https://pbs.twimg.com/media/quoted.jpg"],
                    alt_texts=["Quoted slide"],
                ),
            )
        ],
    )

    with patch(
        "app.adapters.twitter.playwright_extractor.extract_tweet",
        new=AsyncMock(return_value=result),
    ):
        _content_text, _content_source, metadata = await extractor.extract(
            url_text="https://x.com/user/status/1",
            tweet_id="1",
            is_article=False,
            correlation_id="cid",
            metadata={},
            timeout_ms=15000,
        )

    assert metadata["quoted_post_media_policy"] == "included_with_role_annotation"
    assert metadata["quoted_post_media_included"] is True
    assert metadata["tweet_media"][0]["from_quoted_post"] is True
    assert metadata["tweet_media"][0]["quoted_by_tweet_id"] == "1"


def test_playwright_detects_article_redirect_from_single_url_tweet() -> None:
    tweets = [
        TweetData(
            tweet_id="1",
            author="User",
            order=0,
            text="https://x.com/i/article/42",
            author_handle="u",
        )
    ]
    assert (
        TwitterPlaywrightExtractor.detect_article_redirect(tweets) == "https://x.com/i/article/42"
    )


@pytest.mark.asyncio
async def test_playwright_expands_tco_urls_with_cap() -> None:
    extractor = TwitterPlaywrightExtractor(
        cfg=_make_cfg(playwright_enabled=True), request_repo=MagicMock()
    )
    tweets = [
        TweetData(
            tweet_id=str(i),
            author="User",
            order=i,
            text=f"https://t.co/{i}",
            author_handle="u",
        )
        for i in range(25)
    ]

    async def _resolve(url: str) -> str:
        return url.replace("https://t.co/", "https://example.com/")

    with patch(
        "app.adapters.twitter.playwright_extractor.resolve_tco_url",
        new=AsyncMock(side_effect=_resolve),
    ):
        await extractor.expand_tco_urls_in_tweets(tweets, "cid")

    assert tweets[0].text == "https://example.com/0"
    assert tweets[19].text == "https://example.com/19"
    assert tweets[24].text == "https://t.co/24"


@pytest.mark.asyncio
async def test_empty_output_uses_resolve_failed_reason_and_notifies_interactive_mode() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=False),
        crawl_result=SimpleNamespace(status="error", content_markdown=None, content_html=None),
    )
    coordinator: Any = extractor._coordinator
    resolution = TwitterArticleLinkResolution(
        input_url="https://t.co/abc",
        resolved_url=None,
        canonical_url=None,
        article_id=None,
        is_article=False,
        reason="resolve_failed",
    )

    with patch(
        "app.adapters.twitter.extraction_coordinator.resolve_twitter_article_link",
        new=AsyncMock(return_value=resolution),
    ):
        coordinator._firecrawl_extractor.extract = AsyncMock(return_value=(False, "", "none"))
        with pytest.raises(ValueError, match="Twitter content extraction"):
            await extractor.extract(
                _make_request(url_text="https://t.co/abc", mode="interactive", silent=False)
            )

    coordinator._response_formatter.send_error_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_pure_mode_suppresses_accept_notification() -> None:
    extractor: Any = _make_platform_extractor(
        cfg=_make_cfg(playwright_enabled=False),
        crawl_result=SimpleNamespace(status="ok", content_markdown="body", content_html=None),
    )
    coordinator: Any = extractor._coordinator
    coordinator._firecrawl_extractor.extract = AsyncMock(return_value=(True, "body", "markdown"))

    await extractor.extract(_make_request(url_text="https://x.com/user/status/1", mode="pure"))

    coordinator._lifecycle.send_accepted_notification.assert_not_awaited()
