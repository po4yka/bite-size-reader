"""Direct HTML fetch provider (httpx + trafilatura fallback)."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.html_utils import html_to_text

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 400
_DEFAULT_TIMEOUT_SEC = 30
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
}


class DirectHTMLProvider:
    """Tertiary fallback: fetch raw HTML and convert to text."""

    def __init__(self, timeout_sec: int = _DEFAULT_TIMEOUT_SEC) -> None:
        self._timeout_sec = timeout_sec

    @property
    def provider_name(self) -> str:
        return "direct_html"

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        started = time.perf_counter()
        try:
            html = await self._fetch_html(url)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            logger.debug(
                "direct_html_fetch_failed",
                extra={"url": url, "error": str(exc), "error_type": type(exc).__name__},
            )
            return FirecrawlResult(
                status="error",
                error_text=f"Direct HTML fetch failed: {exc}",
                latency_ms=latency,
                source_url=url,
                endpoint="direct_html",
            )

        latency = int((time.perf_counter() - started) * 1000)

        if not html:
            return FirecrawlResult(
                status="error",
                error_text="Direct HTML: no usable content",
                latency_ms=latency,
                source_url=url,
                endpoint="direct_html",
            )

        content_text = html_to_text(html)
        if len(content_text) < _MIN_TEXT_LENGTH:
            return FirecrawlResult(
                status="error",
                error_text=f"Direct HTML: content too short ({len(content_text)} chars)",
                content_html=html,
                latency_ms=latency,
                source_url=url,
                endpoint="direct_html",
            )

        return FirecrawlResult(
            status="ok",
            http_status=200,
            content_markdown=None,
            content_html=html,
            latency_ms=latency,
            source_url=url,
            endpoint="direct_html",
            options_json={"direct_fetch": True},
        )

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch raw HTML with streaming and size limits."""
        overall_timeout = self._timeout_sec + 5
        async with asyncio.timeout(overall_timeout):
            async with (
                httpx.AsyncClient(follow_redirects=True, timeout=self._timeout_sec) as client,
                client.stream("GET", url, headers=_HEADERS) as resp,
            ):
                ctype = resp.headers.get("content-type", "").lower()
                if resp.status_code != 200 or "text/html" not in ctype:
                    return None

                content_length = resp.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > _MAX_RESPONSE_BYTES:
                            return None
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        return None
                    chunks.append(chunk)

                encoding = resp.encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace")

    async def aclose(self) -> None:
        pass
