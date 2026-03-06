"""Playwright-based fallback provider for JS-rendered pages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, cast

from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.html_utils import html_to_text

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 400
_DEFAULT_TIMEOUT_SEC = 30

_DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_MOBILE_VIEWPORT = {"width": 390, "height": 844}
_DESKTOP_VIEWPORT = {"width": 1366, "height": 768}


class PlaywrightProvider:
    """Browser-rendered fallback for pages requiring JavaScript execution."""

    def __init__(self, timeout_sec: int = _DEFAULT_TIMEOUT_SEC, headless: bool = True) -> None:
        self._timeout_sec = timeout_sec
        self._headless = headless

    @property
    def provider_name(self) -> str:
        return "playwright"

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        started = time.perf_counter()
        try:
            html = await asyncio.wait_for(
                self._render_html(url, mobile=mobile),
                timeout=self._timeout_sec + 5,
            )
        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "playwright_timeout",
                extra={"url": url, "timeout_sec": self._timeout_sec, "request_id": request_id},
            )
            return FirecrawlResult(
                status="error",
                error_text=f"Playwright timeout after {self._timeout_sec}s",
                latency_ms=latency,
                source_url=url,
                endpoint="playwright",
            )
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "playwright_error",
                extra={
                    "url": url,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "request_id": request_id,
                },
            )
            return FirecrawlResult(
                status="error",
                error_text=f"Playwright error: {exc}",
                latency_ms=latency,
                source_url=url,
                endpoint="playwright",
            )

        latency = int((time.perf_counter() - started) * 1000)
        if not html:
            return FirecrawlResult(
                status="error",
                error_text="Playwright: no usable content",
                latency_ms=latency,
                source_url=url,
                endpoint="playwright",
            )

        content_text = html_to_text(html)
        if len(content_text) < _MIN_TEXT_LENGTH:
            return FirecrawlResult(
                status="error",
                error_text=f"Playwright: content too short ({len(content_text)} chars)",
                content_html=html,
                latency_ms=latency,
                source_url=url,
                endpoint="playwright",
            )

        return FirecrawlResult(
            status="ok",
            http_status=200,
            content_markdown=None,
            content_html=html,
            latency_ms=latency,
            source_url=url,
            endpoint="playwright",
            options_json={
                "provider": "playwright",
                "headless": self._headless,
                "mobile": mobile,
            },
        )

    async def _render_html(self, url: str, *, mobile: bool = True) -> str | None:
        return await asyncio.to_thread(self._render_html_sync, url, mobile=mobile)

    def _render_html_sync(self, url: str, *, mobile: bool = True) -> str | None:
        try:
            from playwright.sync_api import (
                Error as PlaywrightError,
                TimeoutError as PlaywrightTimeoutError,
                sync_playwright,
            )
        except ImportError as exc:
            msg = (
                "Playwright is required for scraper fallback. "
                "Install with: pip install 'playwright>=1.40' && playwright install chromium"
            )
            raise ImportError(msg) from exc

        timeout_ms = max(1_000, int(self._timeout_sec * 1000))
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            if mobile:
                context = browser.new_context(
                    user_agent=_DESKTOP_USER_AGENT,
                    viewport=cast("Any", _MOBILE_VIEWPORT),
                    is_mobile=True,
                    has_touch=True,
                )
            else:
                context = browser.new_context(
                    user_agent=_DESKTOP_USER_AGENT,
                    viewport=cast("Any", _DESKTOP_VIEWPORT),
                )
            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except (PlaywrightTimeoutError, PlaywrightError):
                    logger.debug(
                        "playwright_goto_failed_partial_capture_mode",
                        extra={"url": url},
                        exc_info=True,
                    )

                # Try to trigger lazy-loading content without over-delaying fallback chain.
                for _ in range(4):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(250)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(200)

                try:
                    page.wait_for_load_state("networkidle", timeout=min(5_000, timeout_ms))
                except (PlaywrightTimeoutError, PlaywrightError):
                    logger.debug(
                        "playwright_networkidle_wait_failed",
                        extra={"url": url},
                        exc_info=True,
                    )

                return page.content()
            finally:
                page.close()
                context.close()
                browser.close()

    async def aclose(self) -> None:
        pass
