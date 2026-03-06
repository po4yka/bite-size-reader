"""Content scraper protocol for multi-provider extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.models import FirecrawlResult


@runtime_checkable
class ContentScraperProtocol(Protocol):
    """Protocol for content scraping providers.

    All providers return FirecrawlResult to maintain a single output contract
    used by downstream consumers (quality filters, content cleaning, persistence).
    """

    @property
    def provider_name(self) -> str: ...

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult: ...

    async def aclose(self) -> None: ...
