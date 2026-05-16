"""Shared stubs for scraper tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.call_status import CallStatus


@dataclass
class _MockProvider:
    """Minimal ContentScraperProtocol-conformant stub."""

    name: str = "mock"
    result: FirecrawlResult | None = None
    exception: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    @property
    def provider_name(self) -> str:
        return self.name

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        self.calls.append({"url": url, "mobile": mobile, "request_id": request_id})
        if self.exception is not None:
            raise self.exception
        assert self.result is not None, "MockProvider.result must be set if no exception"
        return self.result

    async def aclose(self) -> None:
        self.closed = True


def _ok_result(url: str = "https://example.com", markdown: str = "# OK") -> FirecrawlResult:
    return FirecrawlResult(
        status=CallStatus.OK,
        http_status=200,
        content_markdown=markdown,
        source_url=url,
        endpoint="mock",
    )


def _error_result(
    url: str = "https://example.com",
    error: str = "provider failed",
) -> FirecrawlResult:
    return FirecrawlResult(
        status=CallStatus.ERROR,
        error_text=error,
        source_url=url,
        endpoint="mock",
    )
