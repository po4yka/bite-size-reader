"""Firecrawl-based content extraction provider (wraps existing FirecrawlClient)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.client import FirecrawlClient
    from app.adapters.external.firecrawl.models import FirecrawlResult


class FirecrawlProvider:
    """Scraper provider backed by FirecrawlClient (cloud or self-hosted)."""

    def __init__(self, client: FirecrawlClient, *, name: str = "firecrawl") -> None:
        self._client = client
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        return await self._client.scrape_markdown(url, mobile=mobile, request_id=request_id)

    async def aclose(self) -> None:
        await self._client.aclose()
