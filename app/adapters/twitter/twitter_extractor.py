"""High-level Twitter/X content extraction orchestrator.

Follows the YouTubeDownloader pattern: lazy-init, semaphore-gated,
two-tier extraction (Firecrawl -> Playwright fallback).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.adapters.content.quality_filters import detect_low_value_content
from app.adapters.twitter.article_link_resolver import (
    TwitterArticleLinkResolution,
    resolve_twitter_article_link,
)
from app.adapters.twitter.article_quality import is_low_quality_article_content
from app.adapters.twitter.text_formatter import (
    BAD_TITLES,
    _has_article_header,
    format_article_for_summary,
    format_tweets_for_summary,
    parse_article_header,
)
from app.config.scraper import profile_timeout_multiplier
from app.core.async_utils import raise_if_cancelled
from app.core.html_utils import clean_markdown_article_text, html_to_text
from app.core.lang import detect_language
from app.core.url_utils import (
    canonicalize_twitter_url,
    compute_dedupe_hash,
    extract_tweet_id,
    extract_twitter_article_id,
    is_twitter_article_url,
    normalize_url,
)
from app.observability.failure_observability import (
    REASON_EXTRACTION_EMPTY_OUTPUT,
    REASON_FIRECRAWL_ERROR,
    REASON_FIRECRAWL_LOW_VALUE,
    REASON_PLAYWRIGHT_EMPTY_CONTENT,
    REASON_PLAYWRIGHT_UI_OR_LOGIN,
    REASON_RESOLVE_FAILED,
    persist_request_failure,
)
from app.observability.metrics import (
    record_twitter_article_extraction,
    record_twitter_article_resolution,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.firecrawl_parser import FirecrawlClient
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.twitter.graphql_parser import TweetData
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.persistence.message_persistence import MessagePersistence

logger = logging.getLogger(__name__)
_TCO_URL_RE = re.compile(r"https?://t\.co/[A-Za-z0-9]+", re.IGNORECASE)
_MAX_TCO_EXPANSIONS = 20
_ARTICLE_REDIRECT_HOSTS = {
    "x.com",
    "twitter.com",
    "www.x.com",
    "www.twitter.com",
    "mobile.x.com",
    "mobile.twitter.com",
    "t.co",
}


class TwitterExtractor:
    """Extracts content from Twitter/X URLs.

    Two-tier strategy:
      Tier 1: Firecrawl (free, works for some public tweets)
      Tier 2: Playwright + cookies (if enabled and Firecrawl fails)
    """

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        firecrawl: FirecrawlClient,
        response_formatter: ResponseFormatter,
        message_persistence: MessagePersistence,
        firecrawl_sem: Callable[[], Any],
        handle_request_dedupe_or_create: Callable[..., Any],
        schedule_crawl_persistence: Callable[..., Any],
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._firecrawl = firecrawl
        self._response_formatter = response_formatter
        self._message_persistence = message_persistence
        self._firecrawl_sem = firecrawl_sem
        self._handle_request_dedupe_or_create = handle_request_dedupe_or_create
        self._schedule_crawl_persistence = schedule_crawl_persistence
        browser_limit = max(1, int(getattr(cfg.twitter, "max_concurrent_browsers", 2)))
        self._pw_sem = asyncio.Semaphore(browser_limit)
        self._cookies_path = Path(cfg.twitter.cookies_path)

    async def extract_and_process(
        self,
        message: Any,
        url_text: str,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> tuple[int, str, str, str, dict[str, Any]]:
        """Extract Twitter/X content with two-tier strategy.

        Returns:
            (req_id, content_text, content_source, detected_lang, metadata)
        """
        norm = normalize_url(url_text)
        tweet_id = extract_tweet_id(url_text)
        is_article = is_twitter_article_url(url_text)
        article_id = extract_twitter_article_id(url_text) if is_article else None

        if not self._cfg.twitter.prefer_firecrawl and not self._cfg.twitter.playwright_enabled:
            error_msg = (
                "Twitter extraction misconfigured: both Firecrawl and Playwright are disabled. "
                "Enable at least one extraction tier."
            )
            raise ValueError(error_msg)

        extraction_url, article_resolution = await self._resolve_article_link(
            url_text=url_text,
            tweet_id=tweet_id,
            is_article=is_article,
            correlation_id=correlation_id,
        )
        if article_resolution.is_article:
            is_article = True
            article_id = article_resolution.article_id or article_id

        dedupe_source = (
            article_resolution.canonical_url or article_resolution.resolved_url or url_text
        )
        dedupe = compute_dedupe_hash(dedupe_source if is_article else url_text)
        await self._response_formatter.send_url_accepted_notification(
            message, norm, correlation_id, silent=silent
        )
        req_id = await self._handle_request_dedupe_or_create(
            message, url_text, norm, dedupe, correlation_id
        )

        content_text = ""
        content_source = "none"
        tier_mode = self._twitter_force_tier()
        run_firecrawl_tier = self._run_firecrawl_tier()
        run_playwright_tier = self._run_playwright_tier()

        metadata: dict[str, Any] = {
            "source": "twitter",
            "tweet_id": tweet_id,
            "is_article": is_article,
            "article_id": article_id,
            "tier_mode": tier_mode,
            "article_resolution_reason": article_resolution.reason,
            "article_resolved_url": article_resolution.resolved_url,
            "article_canonical_url": article_resolution.canonical_url,
            "article_extraction_stage": None,
            "tier_outcomes": {"firecrawl": "skipped", "playwright": "skipped"},
        }

        # Tier 1: Try Firecrawl first (if preferred)
        firecrawl_ok = False
        if run_firecrawl_tier:
            firecrawl_ok, content_text, content_source = await self._try_firecrawl(
                extraction_url, req_id, tweet_id, metadata, correlation_id, is_article
            )
            metadata["tier_outcomes"]["firecrawl"] = "success" if firecrawl_ok else "failed"
        else:
            metadata["tier_outcomes"]["firecrawl"] = (
                "forced_skip" if tier_mode == "playwright" else "disabled"
            )

        # Tier 2: Playwright fallback (if Firecrawl failed and Playwright is enabled)
        should_try_playwright = run_playwright_tier and (
            tier_mode == "playwright" or not firecrawl_ok
        )
        if should_try_playwright:
            try:
                pw_text, pw_source, pw_metadata = await self._extract_playwright(
                    extraction_url,
                    tweet_id,
                    is_article,
                    correlation_id,
                    metadata,
                    request_id=req_id,
                )
                content_text = pw_text
                content_source = pw_source
                if pw_metadata is not metadata:
                    metadata.update(pw_metadata)
                metadata["tier_outcomes"]["playwright"] = "success"
            except Exception as e:
                raise_if_cancelled(e)
                metadata["tier_outcomes"]["playwright"] = "failed"
                logger.warning(
                    "twitter_playwright_failed",
                    extra={
                        "cid": correlation_id,
                        "error": str(e),
                        "tweet_id": tweet_id,
                        "article_id": article_id,
                    },
                )
        elif not run_playwright_tier:
            metadata["tier_outcomes"]["playwright"] = (
                "forced_skip" if tier_mode == "firecrawl" else "disabled"
            )

        if not content_text:
            error_msg = self._build_extraction_error_message()
            reason_code = (
                REASON_RESOLVE_FAILED
                if metadata.get("article_resolution_reason") == "resolve_failed"
                else REASON_EXTRACTION_EMPTY_OUTPUT
            )
            await persist_request_failure(
                request_repo=self._message_persistence.request_repo,
                logger=logger,
                request_id=req_id,
                correlation_id=correlation_id,
                stage="extraction",
                component="platform_router",
                reason_code=reason_code,
                error=ValueError(error_msg),
                retryable=True,
                source_url=url_text,
                resolved_url=metadata.get("article_resolved_url"),
                canonical_url=metadata.get("article_canonical_url"),
                article_id=metadata.get("article_id"),
                content_signals={
                    "tier_outcomes": metadata.get("tier_outcomes"),
                    "is_article": is_article,
                },
            )
            await self._response_formatter.send_error_notification(
                message, "twitter_extraction_error", correlation_id, details=error_msg
            )
            raise ValueError(error_msg)

        detected = detect_language(content_text)
        try:
            await self._message_persistence.request_repo.async_update_request_lang_detected(
                req_id, detected
            )
        except Exception as e:
            raise_if_cancelled(e)
            logger.error(
                "persist_lang_detected_error", extra={"error": str(e), "cid": correlation_id}
            )

        return req_id, content_text, content_source, detected, metadata

    async def extract_content_pure(
        self,
        url_text: str,
        correlation_id: str | None = None,
        request_id: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Extract Twitter/X content without request creation or notifications."""
        tweet_id = extract_tweet_id(url_text)
        is_article = is_twitter_article_url(url_text)
        article_id = extract_twitter_article_id(url_text) if is_article else None
        extraction_url, article_resolution = await self._resolve_article_link(
            url_text=url_text,
            tweet_id=tweet_id,
            is_article=is_article,
            correlation_id=correlation_id,
        )
        if article_resolution.is_article:
            is_article = True
            article_id = article_resolution.article_id or article_id

        tier_mode = self._twitter_force_tier()
        run_firecrawl_tier = self._run_firecrawl_tier()
        run_playwright_tier = self._run_playwright_tier()

        metadata: dict[str, Any] = {
            "source": "twitter",
            "tweet_id": tweet_id,
            "is_article": is_article,
            "article_id": article_id,
            "tier_mode": tier_mode,
            "article_resolution_reason": article_resolution.reason,
            "article_resolved_url": article_resolution.resolved_url,
            "article_canonical_url": article_resolution.canonical_url,
            "article_extraction_stage": None,
            "tier_outcomes": {"firecrawl": "skipped", "playwright": "skipped"},
        }
        content_text = ""
        content_source = "none"

        if not self._cfg.twitter.prefer_firecrawl and not self._cfg.twitter.playwright_enabled:
            raise ValueError(self._build_extraction_error_message())

        firecrawl_ok = False
        if run_firecrawl_tier:
            firecrawl_ok, content_text, content_source = await self._try_firecrawl(
                url_text=extraction_url,
                req_id=request_id,
                tweet_id=tweet_id,
                metadata=metadata,
                correlation_id=correlation_id,
                is_article=is_article,
                persist_result=False,
            )
            metadata["tier_outcomes"]["firecrawl"] = "success" if firecrawl_ok else "failed"
        else:
            metadata["tier_outcomes"]["firecrawl"] = (
                "forced_skip" if tier_mode == "playwright" else "disabled"
            )

        should_try_playwright = run_playwright_tier and (
            tier_mode == "playwright" or not firecrawl_ok
        )
        if should_try_playwright:
            try:
                pw_text, pw_source, pw_metadata = await self._extract_playwright(
                    url_text=extraction_url,
                    tweet_id=tweet_id,
                    is_article=is_article,
                    correlation_id=correlation_id,
                    metadata=metadata,
                    request_id=request_id,
                )
                content_text = pw_text
                content_source = pw_source
                if pw_metadata is not metadata:
                    metadata.update(pw_metadata)
                metadata["tier_outcomes"]["playwright"] = "success"
            except Exception:
                metadata["tier_outcomes"]["playwright"] = "failed"
                raise
        elif not run_playwright_tier:
            metadata["tier_outcomes"]["playwright"] = (
                "forced_skip" if tier_mode == "firecrawl" else "disabled"
            )

        if not content_text:
            reason_code = (
                REASON_RESOLVE_FAILED
                if metadata.get("article_resolution_reason") == "resolve_failed"
                else REASON_EXTRACTION_EMPTY_OUTPUT
            )
            if request_id is not None:
                await persist_request_failure(
                    request_repo=self._message_persistence.request_repo,
                    logger=logger,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    stage="extraction",
                    component="platform_router",
                    reason_code=reason_code,
                    error=ValueError(self._build_extraction_error_message()),
                    retryable=True,
                    source_url=url_text,
                    resolved_url=metadata.get("article_resolved_url"),
                    canonical_url=metadata.get("article_canonical_url"),
                    article_id=metadata.get("article_id"),
                    content_signals={"tier_outcomes": metadata.get("tier_outcomes")},
                )
            raise ValueError(self._build_extraction_error_message())

        return content_text, content_source, metadata

    async def _resolve_article_link(
        self,
        *,
        url_text: str,
        tweet_id: str | None,
        is_article: bool,
        correlation_id: str | None,
    ) -> tuple[str, TwitterArticleLinkResolution]:
        """Resolve article links without affecting tweet/thread URLs."""
        default_result = TwitterArticleLinkResolution(
            input_url=url_text,
            resolved_url=url_text if is_article else None,
            canonical_url=canonicalize_twitter_url(url_text) if is_article else None,
            article_id=extract_twitter_article_id(url_text) if is_article else None,
            is_article=is_article,
            reason="path_match" if is_article else "not_article",
        )

        if is_article:
            record_twitter_article_resolution(status="hit", reason="path_match")
            return default_result.canonical_url or url_text, default_result

        if tweet_id:
            return url_text, default_result

        if not self._cfg.twitter.article_redirect_resolution_enabled:
            return url_text, default_result

        host = (self._safe_hostname(url_text) or "").lower()
        if host not in _ARTICLE_REDIRECT_HOSTS:
            return url_text, default_result

        logger.info(
            "twitter_article_resolution_attempt",
            extra={"cid": correlation_id, "url": url_text, "host": host},
        )
        started = time.perf_counter()
        resolution = await resolve_twitter_article_link(
            url_text,
            timeout_s=self._cfg.twitter.article_resolution_timeout_sec,
        )
        elapsed = max(0.0, time.perf_counter() - started)

        status = "hit" if resolution.is_article else "miss"
        if resolution.reason == "resolve_failed":
            status = "error"
        record_twitter_article_resolution(
            status=status, reason=resolution.reason, latency_seconds=elapsed
        )

        logger.info(
            "twitter_article_resolution_result",
            extra={
                "cid": correlation_id,
                "reason": resolution.reason,
                "is_article": resolution.is_article,
                "resolved_url": resolution.resolved_url,
                "canonical_url": resolution.canonical_url,
                "article_id": resolution.article_id,
                "latency_ms": int(elapsed * 1000),
            },
        )

        if resolution.is_article:
            resolved_target = resolution.canonical_url or resolution.resolved_url or url_text
            return resolved_target, resolution
        return url_text, resolution

    @staticmethod
    def _safe_hostname(url: str) -> str | None:
        try:
            candidate = url.strip()
            if "://" not in candidate:
                candidate = f"https://{candidate}"
            return urlparse(candidate).hostname
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Tier 1: Firecrawl
    # ------------------------------------------------------------------

    async def _try_firecrawl(
        self,
        url_text: str,
        req_id: int | None,
        tweet_id: str | None,
        metadata: dict[str, Any],
        correlation_id: str | None,
        is_article: bool,
        persist_result: bool = True,
    ) -> tuple[bool, str, str]:
        """Attempt Twitter extraction via Firecrawl.

        Returns:
            (success, content_text, content_source)
        """
        try:
            async with self._firecrawl_sem():
                crawl = await self._firecrawl.scrape_markdown(url_text, request_id=req_id)

            if persist_result and req_id is not None:
                self._schedule_crawl_persistence(req_id, crawl, correlation_id)

            quality_issue = detect_low_value_content(crawl)
            if quality_issue and self._can_accept_low_value_firecrawl_content(
                quality_issue, is_article
            ):
                logger.info(
                    "twitter_firecrawl_accept_short_content",
                    extra={
                        "cid": correlation_id,
                        "tweet_id": tweet_id,
                        "quality_reason": quality_issue.get("reason"),
                    },
                )
                quality_issue = None
            if quality_issue and is_article:
                metadata["article_firecrawl_quality_reason"] = quality_issue.get("reason")
                logger.info(
                    "twitter_article_firecrawl_quality_fail",
                    extra={
                        "cid": correlation_id,
                        "reason": quality_issue.get("reason"),
                        "metrics": quality_issue.get("metrics"),
                    },
                )

            has_content = bool(
                crawl.status == "ok"
                and not quality_issue
                and (
                    (crawl.content_markdown and crawl.content_markdown.strip())
                    or (crawl.content_html and crawl.content_html.strip())
                )
            )

            if has_content:
                if crawl.content_markdown and crawl.content_markdown.strip():
                    content_text = clean_markdown_article_text(crawl.content_markdown)
                    content_source = "markdown"
                elif crawl.content_html and crawl.content_html.strip():
                    content_text = html_to_text(crawl.content_html)
                    content_source = "html"
                else:
                    return False, "", "none"

                if is_article and self._is_low_quality_article_content(content_text):
                    metadata["article_firecrawl_quality_reason"] = "ui_or_login"
                    logger.info(
                        "twitter_article_firecrawl_quality_fail",
                        extra={"cid": correlation_id, "reason": "ui_or_login"},
                    )
                    record_twitter_article_extraction(
                        stage="firecrawl",
                        status="failed",
                        reason="ui_or_login",
                    )
                    if req_id is not None:
                        await persist_request_failure(
                            request_repo=self._message_persistence.request_repo,
                            logger=logger,
                            request_id=req_id,
                            correlation_id=correlation_id,
                            stage="extraction",
                            component="twitter_firecrawl",
                            reason_code=REASON_FIRECRAWL_LOW_VALUE,
                            error=ValueError(
                                "Firecrawl article extraction produced UI/login content"
                            ),
                            retryable=True,
                            source_url=url_text,
                            quality_reason="ui_or_login",
                        )
                    return False, "", "none"

                metadata["extraction_method"] = "firecrawl"
                if is_article:
                    metadata["article_extraction_stage"] = "firecrawl"
                logger.info(
                    "twitter_firecrawl_success",
                    extra={
                        "cid": correlation_id,
                        "content_len": len(content_text),
                        "tweet_id": tweet_id,
                    },
                )
                if is_article:
                    logger.info(
                        "twitter_article_extraction_success",
                        extra={
                            "cid": correlation_id,
                            "stage": "firecrawl",
                            "content_len": len(content_text),
                            "article_id": metadata.get("article_id"),
                        },
                    )
                    record_twitter_article_extraction(
                        stage="firecrawl",
                        status="success",
                        reason="ok",
                    )
                return True, content_text, content_source
        except Exception as e:
            raise_if_cancelled(e)
            logger.warning(
                "twitter_firecrawl_failed",
                extra={"cid": correlation_id, "error": str(e), "tweet_id": tweet_id},
            )
            if is_article:
                record_twitter_article_extraction(
                    stage="firecrawl",
                    status="failed",
                    reason="exception",
                )
                if req_id is not None:
                    await persist_request_failure(
                        request_repo=self._message_persistence.request_repo,
                        logger=logger,
                        request_id=req_id,
                        correlation_id=correlation_id,
                        stage="extraction",
                        component="twitter_firecrawl",
                        reason_code=REASON_FIRECRAWL_ERROR,
                        error=e,
                        retryable=True,
                        source_url=url_text,
                    )

        return False, "", "none"

    def _build_extraction_error_message(self) -> str:
        """Build a consistent error message for failed/misconfigured extraction."""
        tier_mode = self._twitter_force_tier()
        if not self._cfg.twitter.prefer_firecrawl and not self._cfg.twitter.playwright_enabled:
            return (
                "Twitter extraction misconfigured: both Firecrawl and Playwright are disabled. "
                "Enable TWITTER_PREFER_FIRECRAWL or TWITTER_PLAYWRIGHT_ENABLED."
            )
        if tier_mode == "firecrawl":
            return "Twitter content extraction failed (forced Firecrawl tier)"
        if tier_mode == "playwright":
            return "Twitter content extraction failed (forced Playwright tier)"
        if not self._cfg.twitter.playwright_enabled:
            return (
                "Twitter content extraction via Firecrawl returned insufficient content. "
                "Enable TWITTER_PLAYWRIGHT_ENABLED for authenticated extraction."
            )
        return "Twitter content extraction failed (both Firecrawl and Playwright)"

    def _twitter_force_tier(self) -> str:
        return str(getattr(self._cfg.twitter, "force_tier", "auto")).strip().lower() or "auto"

    def _run_firecrawl_tier(self) -> bool:
        if self._twitter_force_tier() == "playwright":
            return False
        return bool(getattr(self._cfg.twitter, "prefer_firecrawl", True))

    def _run_playwright_tier(self) -> bool:
        if self._twitter_force_tier() == "firecrawl":
            return False
        return bool(getattr(self._cfg.twitter, "playwright_enabled", False))

    def _twitter_profile(self) -> str:
        twitter_profile = (
            str(getattr(self._cfg.twitter, "scraper_profile", "inherit")).strip().lower()
        )
        if twitter_profile == "inherit":
            scraper_cfg = getattr(self._cfg, "scraper", None)
            inherited = str(getattr(scraper_cfg, "profile", "balanced")).strip().lower()
            return inherited or "balanced"
        return twitter_profile or "balanced"

    def _effective_twitter_timeout_ms(self) -> int:
        multiplier = profile_timeout_multiplier(self._twitter_profile())
        timeout_ms = int(getattr(self._cfg.twitter, "page_timeout_ms", 15_000) * multiplier)
        return max(1_000, timeout_ms)

    # ------------------------------------------------------------------
    # Tier 2: Playwright
    # ------------------------------------------------------------------

    async def _extract_playwright(
        self,
        url_text: str,
        tweet_id: str | None,
        is_article: bool,
        correlation_id: str | None,
        metadata: dict[str, Any],
        request_id: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Extract Twitter content via Playwright browser automation."""
        headless = self._cfg.twitter.headless
        timeout_ms = self._effective_twitter_timeout_ms()
        cookies = self._cookies_path if self._cookies_path.exists() else None

        async with self._pw_sem:
            if is_article:
                content_text, content_source, pw_metadata = await self._pw_extract_article(
                    url=url_text,
                    cookies=cookies,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            else:
                content_text, content_source, pw_metadata = await self._pw_extract_tweet(
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

    async def _pw_extract_tweet(
        self,
        url: str,
        tweet_id: str | None,
        cookies: Path | None,
        headless: bool,
        timeout_ms: int,
        correlation_id: str | None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Extract tweet/thread via GraphQL interception."""
        from app.adapters.twitter.playwright_client import extract_tweet

        result = await extract_tweet(
            url,
            cookies_path=cookies,
            headless=headless,
            timeout_ms=timeout_ms,
            expected_tweet_id=tweet_id,
        )

        if not result.tweets:
            msg = f"Playwright extraction returned no tweets for {url}"
            raise ValueError(msg)

        if tweet_id and all(tweet.tweet_id != tweet_id for tweet in result.tweets):
            msg = f"Playwright extraction did not include requested tweet_id={tweet_id}"
            raise ValueError(msg)

        await self._expand_tco_urls_in_tweets(result.tweets, correlation_id)
        content_text = format_tweets_for_summary(result.tweets)

        pw_metadata: dict[str, Any] = {
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

    async def _pw_extract_article(
        self,
        url: str,
        cookies: Path | None,
        headless: bool,
        timeout_ms: int,
        correlation_id: str | None,
        request_id: int | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Extract X Article via DOM scraping."""
        from app.adapters.twitter.playwright_client import scrape_article

        # Articles need more time to render
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
                stage="playwright", status="failed", reason="empty_content"
            )
            if request_id is not None:
                await persist_request_failure(
                    request_repo=self._message_persistence.request_repo,
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
            msg = f"Playwright article extraction returned no content (reason=empty_content) for {url}"
            raise ValueError(msg)
        if self._is_low_quality_article_content(content):
            record_twitter_article_extraction(
                stage="playwright", status="failed", reason="ui_or_login"
            )
            if request_id is not None:
                await persist_request_failure(
                    request_repo=self._message_persistence.request_repo,
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
            msg = (
                "Playwright article extraction appears to be UI/login content "
                f"(reason=ui_or_login) for {url}"
            )
            raise ValueError(msg)

        # Parse title/author from content text when DOM selectors missed them
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

    async def _expand_tco_urls_in_tweets(
        self,
        tweets: list[TweetData],
        correlation_id: str | None,
    ) -> None:
        """Resolve t.co short links in tweet text for better summarization context."""
        urls = self._collect_tco_urls(tweets)
        if not urls:
            return

        if len(urls) > _MAX_TCO_EXPANSIONS:
            logger.info(
                "twitter_tco_expansion_capped",
                extra={
                    "cid": correlation_id,
                    "detected": len(urls),
                    "cap": _MAX_TCO_EXPANSIONS,
                },
            )
            urls = urls[:_MAX_TCO_EXPANSIONS]

        from app.adapters.twitter.playwright_client import resolve_tco_url

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
            self._apply_tco_replacements(tweet, replacements)

        logger.info(
            "twitter_tco_expanded",
            extra={
                "cid": correlation_id,
                "resolved": len(replacements),
            },
        )

    @staticmethod
    def _collect_tco_urls(tweets: list[TweetData]) -> list[str]:
        """Collect unique t.co URLs from tweets and nested quote tweets."""
        urls: list[str] = []
        seen: set[str] = set()

        def _collect(tweet: TweetData) -> None:
            for match in _TCO_URL_RE.finditer(tweet.text or ""):
                url = match.group(0)
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
            if tweet.quote_tweet:
                _collect(tweet.quote_tweet)

        for tweet in tweets:
            _collect(tweet)

        return urls

    @staticmethod
    def _apply_tco_replacements(tweet: TweetData, replacements: dict[str, str]) -> None:
        """Replace t.co URLs in tweet and nested quote text."""
        tweet.text = _TCO_URL_RE.sub(
            lambda match: replacements.get(match.group(0), match.group(0)),
            tweet.text or "",
        )
        if tweet.quote_tweet:
            TwitterExtractor._apply_tco_replacements(tweet.quote_tweet, replacements)

    @staticmethod
    def _can_accept_low_value_firecrawl_content(
        quality_issue: dict[str, Any],
        is_article: bool,
    ) -> bool:
        """Allow short-but-valid tweet content from Firecrawl."""
        if is_article:
            return False

        reason = str(quality_issue.get("reason") or "")
        return reason in {"content_too_short", "content_low_variation"}

    _is_low_quality_article_content = staticmethod(is_low_quality_article_content)
