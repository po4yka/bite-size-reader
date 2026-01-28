from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.external.firecrawl.constants import FIRECRAWL_SCRAPE_ENDPOINT


class FirecrawlResult(BaseModel):
    """Normalized representation of a Firecrawl `/v2/scrape` response."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="High-level status of the crawl attempt.")
    http_status: int | None = Field(
        default=None, description="HTTP status code returned by Firecrawl."
    )
    content_markdown: str | None = Field(
        default=None, description="Markdown content returned by Firecrawl."
    )
    content_html: str | None = Field(
        default=None, description="HTML content returned by Firecrawl."
    )
    structured_json: dict[str, Any] | None = Field(
        default=None, description="Structured JSON payload from Firecrawl."
    )
    metadata_json: dict[str, Any] | None = Field(
        default=None, description="Metadata block supplied by Firecrawl."
    )
    links_json: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Outbound links metadata from Firecrawl."
    )
    response_success: bool | None = Field(
        default=None, description="Whether Firecrawl reported success."
    )
    response_error_code: str | None = Field(
        default=None, description="Firecrawl-provided error code, if any."
    )
    response_error_message: str | None = Field(
        default=None, description="Firecrawl-provided error message, if any."
    )
    response_details: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Additional detail array/object from Firecrawl."
    )
    latency_ms: int | None = Field(
        default=None, description="Client-observed latency for the call."
    )
    error_text: str | None = Field(
        default=None, description="Client-derived error message, if any."
    )
    source_url: str | None = Field(default=None, description="URL that was submitted to Firecrawl.")
    endpoint: str | None = Field(
        default=FIRECRAWL_SCRAPE_ENDPOINT, description="Firecrawl endpoint that was called."
    )
    options_json: dict[str, Any] | None = Field(
        default=None, description="Options payload sent to Firecrawl."
    )
    correlation_id: str | None = Field(
        default=None, description="Firecrawl correlation identifier (cid)."
    )

    @property
    def success(self) -> bool:
        """Convenience property: True if status is 'success' or response_success is True."""
        return self.status == "success" or self.response_success is True


class FirecrawlSearchItem(BaseModel):
    """Normalized representation of a Firecrawl `/v2/search` result item."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None


class FirecrawlSearchResult(BaseModel):
    """Result container for Firecrawl search queries."""

    status: str
    http_status: int | None = None
    results: list[FirecrawlSearchItem] = Field(default_factory=list)
    total_results: int | None = None
    latency_ms: int | None = None
    error_text: str | None = None
    correlation_id: str | None = None
