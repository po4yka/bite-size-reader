"""Twitter/X content extraction configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class TwitterConfig(BaseModel):
    """Twitter/X content extraction configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="TWITTER_ENABLED",
        description="Enable Twitter/X URL detection and extraction",
    )

    playwright_enabled: bool = Field(
        default=False,
        validation_alias="TWITTER_PLAYWRIGHT_ENABLED",
        description="Enable Playwright-based extraction (requires playwright + chromium)",
    )

    cookies_path: str = Field(
        default="/data/twitter_cookies.txt",
        validation_alias="TWITTER_COOKIES_PATH",
        description="Path to Netscape-format cookies.txt for authenticated extraction",
    )

    headless: bool = Field(
        default=True,
        validation_alias="TWITTER_HEADLESS",
        description="Run Playwright browser in headless mode",
    )

    page_timeout_ms: int = Field(
        default=15000,
        validation_alias="TWITTER_PAGE_TIMEOUT_MS",
        description="Page load timeout in milliseconds for Playwright",
    )

    prefer_firecrawl: bool = Field(
        default=True,
        validation_alias="TWITTER_PREFER_FIRECRAWL",
        description="Try Firecrawl first before falling back to Playwright",
    )

    @field_validator("page_timeout_ms", mode="before")
    @classmethod
    def _parse_timeout(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            return 15000
        try:
            return int(str(value))
        except ValueError as exc:
            msg = "page_timeout_ms must be a valid integer"
            raise ValueError(msg) from exc
