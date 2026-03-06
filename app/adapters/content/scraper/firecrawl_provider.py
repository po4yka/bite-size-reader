"""Firecrawl-based content extraction provider (wraps existing FirecrawlClient)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.content.scraper.runtime_tuning import tuned_firecrawl_wait_for_ms

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.client import FirecrawlClient
    from app.adapters.external.firecrawl.models import FirecrawlResult


class FirecrawlProvider:
    """Scraper provider backed by FirecrawlClient (cloud or self-hosted)."""

    def __init__(
        self,
        client: FirecrawlClient,
        *,
        name: str = "firecrawl",
        wait_for_ms: int = 3000,
        js_heavy_hosts: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._name = name
        self._wait_for_ms = wait_for_ms
        self._js_heavy_hosts = js_heavy_hosts

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
        wait_for_ms = tuned_firecrawl_wait_for_ms(
            base_wait_for_ms=self._wait_for_ms,
            url=url,
            js_heavy_hosts=self._js_heavy_hosts,
        )
        return await self._client.scrape_markdown(
            url,
            mobile=mobile,
            request_id=request_id,
            wait_for_ms_override=wait_for_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
