"""Playwright-based browser automation for Twitter/X content extraction.

Wraps sync Playwright calls in asyncio.to_thread() for async compatibility.
Lazy-imports playwright to fail gracefully when not installed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from pathlib import Path

from app.adapters.twitter.graphql_parser import (
    ExtractionResult,
    TweetData,
    extract_tweets_from_graphql,
)

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _load_cookies_netscape(cookies_path: Path) -> list[dict[str, Any]]:
    """Parse a Netscape-format cookies.txt file into Playwright cookie dicts."""
    cookies: list[dict[str, Any]] = []
    for line in cookies_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, expires, name, value = parts[:7]
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure.upper() == "TRUE",
                "expires": int(expires) if expires != "0" else -1,
            }
        )
    return cookies


def _extract_tweet_sync(
    url: str,
    cookies_path: Path | None = None,
    headless: bool = True,
    timeout_ms: int = 15000,
) -> ExtractionResult:
    """Extract tweet data by intercepting X's GraphQL API via Playwright.

    This is a synchronous function -- call via asyncio.to_thread().
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        msg = (
            "Playwright is required for Twitter extraction. "
            "Install with: pip install 'playwright>=1.40' && playwright install chromium"
        )
        raise ImportError(msg) from exc

    captured_responses: list[dict[str, Any]] = []

    def _on_response(response: Any) -> None:
        try:
            if "TweetDetail" in response.url and response.status == 200:
                captured_responses.append(response.json())
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(user_agent=_USER_AGENT)

        if cookies_path and cookies_path.exists():
            cookies = _load_cookies_netscape(cookies_path)
            if cookies:
                context.add_cookies(cookies)

        page = context.new_page()
        page.on("response", _on_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except Exception:
            pass  # Page may not fully load but we might still capture GraphQL

        # Scroll once to trigger thread loading
        time.sleep(2)
        page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        time.sleep(2)

        page.close()
        browser.close()

    # Parse captured GraphQL responses
    all_tweets: list[TweetData] = []
    seen_ids: set[str] = set()
    for resp_json in captured_responses:
        for tweet in extract_tweets_from_graphql(resp_json):
            if tweet.tweet_id not in seen_ids:
                seen_ids.add(tweet.tweet_id)
                all_tweets.append(tweet)

    # Sort by order
    all_tweets.sort(key=lambda t: t.order)

    return ExtractionResult(url=url, tweets=all_tweets)


def _scrape_article_sync(
    url: str,
    cookies_path: Path | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Extract an X Article by rendering in browser and scraping DOM.

    This is a synchronous function -- call via asyncio.to_thread().
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        msg = (
            "Playwright is required for Twitter extraction. "
            "Install with: pip install 'playwright>=1.40' && playwright install chromium"
        )
        raise ImportError(msg) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(user_agent=_USER_AGENT)

        if cookies_path and cookies_path.exists():
            cookies = _load_cookies_netscape(cookies_path)
            if cookies:
                context.add_cookies(cookies)

        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except Exception:
            pass

        # Wait for content to render
        time.sleep(3)

        # Scroll to bottom to load all content
        prev_height = 0
        for _ in range(20):
            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            time.sleep(1)
            height = page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                break
            prev_height = height

        # Scroll back to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)

        # Extract article content from DOM
        article_data = page.evaluate(
            """() => {
            const result = {title: '', author: '', authorHandle: '', content: '', images: []};

            const h1 = document.querySelector('article h1, [data-testid="article-cover-title"]');
            if (h1) result.title = h1.innerText.trim();

            if (!result.title) {
                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle) result.title = ogTitle.content;
            }

            const authorEl = document.querySelector(
                '[data-testid="User-Name"] a, article [role="link"] span'
            );
            if (authorEl) result.author = authorEl.innerText.trim();

            const articleEl = document.querySelector('article');
            if (articleEl) {
                result.content = articleEl.innerText;
            } else {
                const main = document.querySelector('main [data-testid="primaryColumn"]');
                if (main) result.content = main.innerText;
            }

            return result;
        }"""
        )

        page.close()
        browser.close()

    return article_data


async def resolve_tco_url(short_url: str, timeout: int = 10) -> str | None:
    """Follow a t.co redirect via HTTP and return the resolved URL.

    Args:
        short_url: URL starting with https://t.co/
        timeout: HTTP request timeout in seconds

    Returns:
        Resolved URL string, or None if not a t.co URL or resolution fails
    """
    if not short_url.startswith("https://t.co/"):
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.head(short_url)
            return str(resp.url)
    except Exception:
        return None


async def extract_tweet(
    url: str,
    cookies_path: Path | None = None,
    headless: bool = True,
    timeout_ms: int = 15000,
) -> ExtractionResult:
    """Async wrapper around sync Playwright tweet extraction."""
    return await asyncio.to_thread(
        _extract_tweet_sync,
        url,
        cookies_path=cookies_path,
        headless=headless,
        timeout_ms=timeout_ms,
    )


async def scrape_article(
    url: str,
    cookies_path: Path | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Async wrapper around sync Playwright article extraction."""
    return await asyncio.to_thread(
        _scrape_article_sync,
        url,
        cookies_path=cookies_path,
        headless=headless,
        timeout_ms=timeout_ms,
    )
