"""Deterministic scraper provider used when scraping is explicitly disabled."""

from __future__ import annotations

from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.call_status import CallStatus


class DisabledScraperProvider:
    def __init__(self, reason: str = "Scraper is disabled by configuration") -> None:
        self._reason = reason

    @property
    def provider_name(self) -> str:
        return "scraper_disabled"

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        del mobile, request_id
        return FirecrawlResult(
            status=CallStatus.ERROR,
            error_text=self._reason,
            source_url=url,
            endpoint="scraper_disabled",
        )

    async def aclose(self) -> None:
        return None
