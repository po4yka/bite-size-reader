"""Tests for FirecrawlProvider min_content_length check."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.adapters.content.scraper.firecrawl_provider import FirecrawlProvider
from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.call_status import CallStatus


def _make_client(result: FirecrawlResult) -> AsyncMock:
    client = AsyncMock()
    client.scrape_markdown = AsyncMock(return_value=result)
    client.aclose = AsyncMock()
    return client


class TestFirecrawlProviderContentLength:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_firecrawl_provider_rejects_thin_content(self) -> None:
        """Short nav-stub markdown should be rejected as thin content."""
        thin_markdown = "Navigation menu items and sidebar links. " * 6  # ~270 chars
        ok_result = FirecrawlResult(
            status=CallStatus.OK,
            http_status=200,
            content_markdown=thin_markdown,
            source_url="https://example.com/article",
            endpoint="/v1/scrape",
            latency_ms=150,
        )
        client = _make_client(ok_result)
        provider = FirecrawlProvider(client, min_content_length=400)

        result = await provider.scrape_markdown("https://example.com/article")

        assert result.status == CallStatus.ERROR
        assert "content too short" in (result.error_text or "")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_firecrawl_provider_accepts_sufficient_content(self) -> None:
        """Article with enough content should pass through unchanged."""
        long_markdown = "This is a substantial article paragraph. " * 60  # ~2400 chars
        ok_result = FirecrawlResult(
            status=CallStatus.OK,
            http_status=200,
            content_markdown=long_markdown,
            source_url="https://example.com/article",
            endpoint="/v1/scrape",
            latency_ms=200,
        )
        client = _make_client(ok_result)
        provider = FirecrawlProvider(client, min_content_length=400)

        result = await provider.scrape_markdown("https://example.com/article")

        assert result.status == CallStatus.OK
        assert result.content_markdown == long_markdown

    @pytest.mark.asyncio(loop_scope="function")
    async def test_firecrawl_provider_preserves_html_on_thin_content(self) -> None:
        """When markdown is thin, the original HTML should be preserved for fallback."""
        thin_markdown = "Short." * 5  # 30 chars
        original_html = "<html><body><p>Full article content here...</p></body></html>"
        ok_result = FirecrawlResult(
            status=CallStatus.OK,
            http_status=200,
            content_markdown=thin_markdown,
            content_html=original_html,
            source_url="https://example.com/article",
            endpoint="/v1/scrape",
            latency_ms=120,
        )
        client = _make_client(ok_result)
        provider = FirecrawlProvider(client, min_content_length=400)

        result = await provider.scrape_markdown("https://example.com/article")

        assert result.status == CallStatus.ERROR
        assert result.content_html == original_html
        assert result.latency_ms == 120
        assert result.source_url == "https://example.com/article"
        assert result.endpoint == "/v1/scrape"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_firecrawl_provider_passes_through_errors(self) -> None:
        """Upstream errors should be returned unchanged."""
        error_result = FirecrawlResult(
            status=CallStatus.ERROR,
            error_text="Firecrawl: upstream timeout",
            source_url="https://example.com/article",
            endpoint="/v1/scrape",
            latency_ms=5000,
        )
        client = _make_client(error_result)
        provider = FirecrawlProvider(client, min_content_length=400)

        result = await provider.scrape_markdown("https://example.com/article")

        assert result is error_result
        assert result.status == CallStatus.ERROR
        assert result.error_text == "Firecrawl: upstream timeout"
