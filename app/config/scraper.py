"""Scraper multi-provider configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScraperConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    provider_order: list[str] = Field(
        default=["scrapling", "firecrawl", "playwright", "crawlee", "direct_html"],
        validation_alias="SCRAPER_PROVIDER_ORDER",
        description="Ordered list of scraping providers to try",
    )
    scrapling_enabled: bool = Field(
        default=True,
        validation_alias="SCRAPLING_ENABLED",
    )
    scrapling_timeout_sec: int = Field(
        default=30,
        validation_alias="SCRAPLING_TIMEOUT_SEC",
    )
    scrapling_stealth_fallback: bool = Field(
        default=True,
        validation_alias="SCRAPLING_STEALTH_FALLBACK",
    )
    firecrawl_self_hosted_enabled: bool = Field(
        default=False,
        validation_alias="FIRECRAWL_SELF_HOSTED_ENABLED",
    )
    firecrawl_self_hosted_url: str = Field(
        default="http://firecrawl:3002",
        validation_alias="FIRECRAWL_SELF_HOSTED_URL",
    )
    firecrawl_self_hosted_api_key: str = Field(
        default="fc-bsr-local",
        validation_alias="FIRECRAWL_SELF_HOSTED_API_KEY",
    )
    playwright_enabled: bool = Field(
        default=True,
        validation_alias="SCRAPER_PLAYWRIGHT_ENABLED",
    )
    playwright_headless: bool = Field(
        default=True,
        validation_alias="SCRAPER_PLAYWRIGHT_HEADLESS",
    )
    playwright_timeout_sec: int = Field(
        default=30,
        validation_alias="SCRAPER_PLAYWRIGHT_TIMEOUT_SEC",
    )
    crawlee_enabled: bool = Field(
        default=True,
        validation_alias="SCRAPER_CRAWLEE_ENABLED",
    )
    crawlee_timeout_sec: int = Field(
        default=45,
        validation_alias="SCRAPER_CRAWLEE_TIMEOUT_SEC",
    )
    crawlee_headless: bool = Field(
        default=True,
        validation_alias="SCRAPER_CRAWLEE_HEADLESS",
    )
    crawlee_max_retries: int = Field(
        default=2,
        validation_alias="SCRAPER_CRAWLEE_MAX_RETRIES",
    )
