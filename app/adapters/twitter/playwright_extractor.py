"""Playwright tier for Twitter platform extraction."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from app.adapters.twitter.article_quality import is_low_quality_article_content
from app.adapters.twitter.playwright_client import extract_tweet, resolve_tco_url, scrape_article
from app.adapters.twitter.text_formatter import (
    BAD_TITLES,
    _has_article_header,
    format_article_for_summary,
    format_tweets_for_summary,
    parse_article_header,
)
from app.core.async_utils import raise_if_cancelled
from app.core.url_utils import extract_twitter_article_id, is_twitter_article_url
from app.observability.failure_observability import (
    REASON_PLAYWRIGHT_EMPTY_CONTENT,
    REASON_PLAYWRIGHT_UI_OR_LOGIN,
    persist_request_failure,
)
from app.observability.metrics import record_twitter_article_extraction

logger = logging.getLogger(__name__)
_TCO_URL_RE = re.compile(r"https?://t\.co/[A-Za-z0-9]+", re.IGNORECASE)
_MAX_TCO_EXPANSIONS = 20


class TwitterPlaywrightExtractor:
    """Execute authenticated Playwright extraction for tweets and X articles."""

    def __init__(
        self,
        *,
        cfg: Any,
        request_repo: Any,
    ) -> None:
        self._cfg = cfg
        self._request_repo = request_repo
        browser_limit = max(1, int(getattr(cfg.twitter, "max_concurrent_browsers", 2)))
        self._pw_sem = asyncio.Semaphore(browser_limit)
        self._cookies_path = Path(cfg.twitter.cookies_path)

    async def extract(
        self,
        *,
        url_text: str,
        tweet_id: str | None,
        is_article: bool,
        correlation_id: str | None,
        metadata: dict[str, Any],
        timeout_ms: int,
        request_id: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        headless = self._cfg.twitter.headless
        cookies = self._cookies_path if self._cookies_path.exists() else None

        async with self._pw_sem:
            if is_article:
                content_text, content_source, pw_metadata = await self._extract_article(
                    url=url_text,
                    cookies=cookies,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            else:
                content_text, content_source, pw_metadata = await self._extract_tweet(
                    url=url_text,
                    tweet_id=tweet_id,
                    cookies=cookies,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    correlation_id=correlation_id,
                )

        metadata.update(pw_metadata)
        metadata["extraction_method"] = "playwright"
        if is_article:
            metadata["article_extraction_stage"] = "playwright"
        return content_text, content_source, metadata

    async def _extract_tweet(
        self,
        *,
        url: str,
        tweet_id: str | None,
        cookies: Path | None,
        headless: bool,
        timeout_ms: int,
        correlation_id: str | None,
    ) -> tuple[str, str, dict[str, Any]]:
        result = await extract_tweet(
            url,
            cookies_path=cookies,
            headless=headless,
            timeout_ms=timeout_ms,
            expected_tweet_id=tweet_id,
        )

        if not result.tweets:
            raise ValueError(f"Playwright extraction returned no tweets for {url}")
        if tweet_id and all(tweet.tweet_id != tweet_id for tweet in result.tweets):
            raise ValueError(f"Playwright extraction did not include requested tweet_id={tweet_id}")

        await self.expand_tco_urls_in_tweets(result.tweets, correlation_id)
        article_redirect = self.detect_article_redirect(result.tweets)
        if article_redirect:
            logger.info(
                "twitter_article_redirect_detected",
                extra={
                    "cid": correlation_id,
                    "article_url": article_redirect,
                    "tweet_id": tweet_id,
                },
            )
            content_text, content_source, pw_metadata = await self._extract_article(
                url=article_redirect,
                cookies=cookies,
                headless=headless,
                timeout_ms=timeout_ms,
                correlation_id=correlation_id,
            )
            pw_metadata["article_redirect_from_tweet"] = True
            pw_metadata["original_tweet_id"] = tweet_id
            return content_text, content_source, pw_metadata

        content_text = format_tweets_for_summary(result.tweets)
        pw_metadata = {
            "tweet_count": len(result.tweets),
            "tweet_id": tweet_id or (result.tweets[0].tweet_id if result.tweets else None),
            "author_handle": result.tweets[0].author_handle if result.tweets else None,
            "is_thread": len(result.tweets) > 1,
        }
        logger.info(
            "twitter_playwright_tweet_success",
            extra={
                "cid": correlation_id,
                "tweet_count": len(result.tweets),
                "content_len": len(content_text),
                "tweet_id": tweet_id,
            },
        )
        return content_text, "twitter_graphql", pw_metadata

    async def _extract_article(
        self,
        *,
        url: str,
        cookies: Path | None,
        headless: bool,
        timeout_ms: int,
        correlation_id: str | None,
        request_id: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        article_timeout = max(timeout_ms, 30000)
        article_data = await scrape_article(
            url,
            cookies_path=cookies,
            headless=headless,
            timeout_ms=article_timeout,
        )

        content = (article_data.get("content") or "").strip()
        if not content:
            record_twitter_article_extraction(
                stage="playwright",
                status="failed",
                reason="empty_content",
            )
            if request_id is not None:
                await persist_request_failure(
                    request_repo=self._request_repo,
                    logger=logger,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    stage="extraction",
                    component="twitter_playwright",
                    reason_code=REASON_PLAYWRIGHT_EMPTY_CONTENT,
                    error=ValueError("Playwright article extraction returned no content"),
                    retryable=True,
                    source_url=url,
                )
            raise ValueError(
                f"Playwright article extraction returned no content (reason=empty_content) for {url}"
            )

        if is_low_quality_article_content(content):
            record_twitter_article_extraction(
                stage="playwright",
                status="failed",
                reason="ui_or_login",
            )
            if request_id is not None:
                await persist_request_failure(
                    request_repo=self._request_repo,
                    logger=logger,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    stage="extraction",
                    component="twitter_playwright",
                    reason_code=REASON_PLAYWRIGHT_UI_OR_LOGIN,
                    error=ValueError(
                        "Playwright article extraction appears to be UI/login content"
                    ),
                    retryable=True,
                    source_url=url,
                    quality_reason="ui_or_login",
                )
            raise ValueError(
                "Playwright article extraction appears to be UI/login content "
                f"(reason=ui_or_login) for {url}"
            )

        title = (article_data.get("title") or "").strip()
        author = (article_data.get("author") or "").strip()
        author_handle = (article_data.get("authorHandle") or "").strip()
        if (title in BAD_TITLES or not author) and _has_article_header(content):
            parsed_title, parsed_author, parsed_handle, _ = parse_article_header(content)
            if title in BAD_TITLES and parsed_title:
                article_data["title"] = parsed_title
                title = parsed_title
            if not author and parsed_author:
                article_data["author"] = parsed_author
                author = parsed_author
            if not author_handle and parsed_handle:
                article_data["authorHandle"] = parsed_handle
                author_handle = parsed_handle

        content_text = format_article_for_summary(article_data)
        pw_metadata: dict[str, Any] = {
            "title": title,
            "author": author,
            "author_handle": author_handle,
            "is_article": True,
            "article_id": extract_twitter_article_id(url),
            "article_resolved_url": article_data.get("finalUrl"),
            "article_canonical_url": article_data.get("canonicalUrl"),
        }
        if article_data.get("selectorFallbackUsed"):
            logger.info(
                "twitter_article_playwright_selector_fallback",
                extra={
                    "cid": correlation_id,
                    "selector_source": article_data.get("contentSelector", "unknown"),
                    "url": url,
                },
            )
        logger.info(
            "twitter_playwright_article_success",
            extra={
                "cid": correlation_id,
                "content_len": len(content_text),
                "title": article_data.get("title", "")[:80],
            },
        )
        logger.info(
            "twitter_article_extraction_success",
            extra={
                "cid": correlation_id,
                "stage": "playwright",
                "content_len": len(content_text),
                "article_id": pw_metadata.get("article_id"),
            },
        )
        record_twitter_article_extraction(stage="playwright", status="success", reason="ok")
        return content_text, "twitter_article", pw_metadata

    async def expand_tco_urls_in_tweets(
        self,
        tweets: list[Any],
        correlation_id: str | None,
    ) -> None:
        urls = self.collect_tco_urls(tweets)
        if not urls:
            return
        if len(urls) > _MAX_TCO_EXPANSIONS:
            logger.info(
                "twitter_tco_expansion_capped",
                extra={"cid": correlation_id, "detected": len(urls), "cap": _MAX_TCO_EXPANSIONS},
            )
            urls = urls[:_MAX_TCO_EXPANSIONS]

        resolved_urls = await asyncio.gather(
            *(resolve_tco_url(url) for url in urls),
            return_exceptions=True,
        )
        replacements: dict[str, str] = {}
        for short_url, resolved in zip(urls, resolved_urls, strict=False):
            if isinstance(resolved, Exception):
                raise_if_cancelled(resolved)
                logger.debug(
                    "twitter_tco_resolution_failed",
                    extra={"cid": correlation_id, "url": short_url, "error": str(resolved)},
                )
                continue
            if isinstance(resolved, str) and resolved and resolved != short_url:
                replacements[short_url] = resolved

        if not replacements:
            return
        for tweet in tweets:
            self.apply_tco_replacements(tweet, replacements)
        logger.info(
            "twitter_tco_expanded",
            extra={"cid": correlation_id, "resolved": len(replacements)},
        )

    @staticmethod
    def detect_article_redirect(tweets: list[Any]) -> str | None:
        if not tweets:
            return None
        main_tweet = min(tweets, key=lambda t: t.order)
        text = main_tweet.text.strip()
        url_match = re.match(r"^(https?://\S+)\s*$", text)
        if not url_match:
            return None
        url = url_match.group(1)
        if is_twitter_article_url(url):
            return url
        return None

    @staticmethod
    def collect_tco_urls(tweets: list[Any]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        def _collect(tweet: Any) -> None:
            for match in _TCO_URL_RE.finditer(tweet.text or ""):
                url = match.group(0)
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
            if getattr(tweet, "quote_tweet", None):
                _collect(tweet.quote_tweet)

        for tweet in tweets:
            _collect(tweet)
        return urls

    @staticmethod
    def apply_tco_replacements(tweet: Any, replacements: dict[str, str]) -> None:
        tweet.text = _TCO_URL_RE.sub(
            lambda match: replacements.get(match.group(0), match.group(0)),
            tweet.text or "",
        )
        if getattr(tweet, "quote_tweet", None):
            TwitterPlaywrightExtractor.apply_tco_replacements(tweet.quote_tweet, replacements)
