"""Scrapling-based content extraction provider (in-process, zero external deps)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.adapters.external.firecrawl.models import FirecrawlResult

logger = logging.getLogger(__name__)

_MIN_CONTENT_LENGTH = 400


class ScraplingProvider:
    """Primary scraper using Scrapling library with TLS impersonation."""

    def __init__(
        self,
        timeout_sec: int = 30,
        stealth_fallback: bool = True,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._stealth_fallback = stealth_fallback

    @property
    def provider_name(self) -> str:
        return "scrapling"

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        started = time.perf_counter()
        try:
            content_html, content_text = await asyncio.wait_for(
                self._fetch(url),
                timeout=self._timeout_sec,
            )
        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "scrapling_timeout",
                extra={"url": url, "timeout_sec": self._timeout_sec},
            )
            return FirecrawlResult(
                status="error",
                error_text=f"Scrapling timeout after {self._timeout_sec}s",
                latency_ms=latency,
                source_url=url,
                endpoint="scrapling",
            )
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "scrapling_error",
                extra={"url": url, "error": str(exc), "error_type": type(exc).__name__},
            )
            return FirecrawlResult(
                status="error",
                error_text=f"Scrapling error: {exc}",
                latency_ms=latency,
                source_url=url,
                endpoint="scrapling",
            )

        latency = int((time.perf_counter() - started) * 1000)

        if not content_text or len(content_text) < _MIN_CONTENT_LENGTH:
            logger.info(
                "scrapling_thin_content",
                extra={
                    "url": url,
                    "content_len": len(content_text or ""),
                    "threshold": _MIN_CONTENT_LENGTH,
                },
            )
            return FirecrawlResult(
                status="error",
                error_text="Scrapling: insufficient content extracted",
                content_html=content_html,
                latency_ms=latency,
                source_url=url,
                endpoint="scrapling",
            )

        return FirecrawlResult(
            status="ok",
            http_status=200,
            content_markdown=content_text,
            content_html=content_html,
            latency_ms=latency,
            source_url=url,
            endpoint="scrapling",
            options_json={"provider": "scrapling"},
        )

    async def _fetch(self, url: str) -> tuple[str | None, str | None]:
        """Fetch URL using Scrapling, with optional stealth fallback."""
        loop = asyncio.get_running_loop()

        html, text = await loop.run_in_executor(None, self._sync_fetch_basic, url)
        if text and len(text) >= _MIN_CONTENT_LENGTH:
            return html, text

        if self._stealth_fallback:
            logger.debug("scrapling_stealth_fallback", extra={"url": url})
            html, text = await loop.run_in_executor(None, self._sync_fetch_stealth, url)

        return html, text

    @staticmethod
    def _sync_fetch_basic(url: str) -> tuple[str | None, str | None]:
        """Basic fetch via Scrapling Fetcher (TLS impersonation, fastest)."""
        scrapling_fetcher = _lazy_import_fetcher()
        resp = scrapling_fetcher.get(url)
        html = resp.text if resp.status == 200 else None
        text = _extract_text(html) if html else None
        return html, text

    @staticmethod
    def _sync_fetch_stealth(url: str) -> tuple[str | None, str | None]:
        """Stealth fetch for JS-heavy sites."""
        stealthy_fetcher = _lazy_import_stealthy_fetcher()
        resp = stealthy_fetcher.fetch(url)
        html = resp.text if resp.status == 200 else None
        text = _extract_text(html) if html else None
        return html, text

    async def aclose(self) -> None:
        pass


def _lazy_import_fetcher() -> Any:
    import importlib

    mod = importlib.import_module("scrapling")
    return mod.Fetcher()


def _lazy_import_stealthy_fetcher() -> Any:
    import importlib

    mod = importlib.import_module("scrapling")
    return mod.StealthyFetcher()


def _extract_text(html: str) -> str | None:
    """Extract article text from HTML using trafilatura."""
    import importlib

    trafilatura = importlib.import_module("trafilatura")
    return trafilatura.extract(html, include_comments=False, include_tables=True)
