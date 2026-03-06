"""Twitter/X content extraction configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

_SCRAPER_PROFILES = {"fast", "balanced", "robust", "inherit"}
_FORCE_TIERS = {"auto", "firecrawl", "playwright"}


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

    force_tier: str = Field(
        default="auto",
        validation_alias="TWITTER_FORCE_TIER",
        description="Force extraction tier: auto, firecrawl, playwright",
    )

    scraper_profile: str = Field(
        default="inherit",
        validation_alias="TWITTER_SCRAPER_PROFILE",
        description="Twitter scraper profile override (inherit, fast, balanced, robust)",
    )

    max_concurrent_browsers: int = Field(
        default=2,
        validation_alias="TWITTER_MAX_CONCURRENT_BROWSERS",
        description="Maximum concurrent Twitter Playwright browser sessions",
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

    article_redirect_resolution_enabled: bool = Field(
        default=True,
        validation_alias="TWITTER_ARTICLE_REDIRECT_RESOLUTION_ENABLED",
        description="Resolve redirects/canonical hints for X Article links before extraction",
    )

    article_resolution_timeout_sec: float = Field(
        default=5.0,
        validation_alias="TWITTER_ARTICLE_RESOLUTION_TIMEOUT_SEC",
        description="Timeout in seconds for resolving redirected X Article links",
    )

    article_live_smoke_enabled: bool = Field(
        default=False,
        validation_alias="TWITTER_ARTICLE_LIVE_SMOKE_ENABLED",
        description="Enable optional live smoke checks for X Article extraction",
    )

    @field_validator("force_tier", mode="before")
    @classmethod
    def _validate_force_tier(cls, value: Any) -> str:
        tier = str(value or "auto").strip().lower()
        if tier not in _FORCE_TIERS:
            msg = "TWITTER_FORCE_TIER must be one of: auto, firecrawl, playwright"
            raise ValueError(msg)
        return tier

    @field_validator("scraper_profile", mode="before")
    @classmethod
    def _validate_scraper_profile(cls, value: Any) -> str:
        profile = str(value or "inherit").strip().lower()
        if profile not in _SCRAPER_PROFILES:
            msg = "TWITTER_SCRAPER_PROFILE must be one of: inherit, fast, balanced, robust"
            raise ValueError(msg)
        return profile

    @field_validator("max_concurrent_browsers", mode="before")
    @classmethod
    def _validate_max_concurrent_browsers(cls, value: Any) -> int:
        raw = 2 if value in (None, "") else value
        try:
            parsed = int(str(raw))
        except ValueError as exc:
            msg = "TWITTER_MAX_CONCURRENT_BROWSERS must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 20:
            msg = "TWITTER_MAX_CONCURRENT_BROWSERS must be between 1 and 20"
            raise ValueError(msg)
        return parsed

    @field_validator("page_timeout_ms", mode="before")
    @classmethod
    def _parse_timeout(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            return 15000
        try:
            timeout = int(str(value))
        except ValueError as exc:
            msg = "page_timeout_ms must be a valid integer"
            raise ValueError(msg) from exc
        if timeout < 500 or timeout > 120_000:
            msg = "page_timeout_ms must be between 500 and 120000"
            raise ValueError(msg)
        return timeout

    @field_validator("article_resolution_timeout_sec", mode="before")
    @classmethod
    def _parse_article_resolution_timeout(cls, value: Any, info: ValidationInfo) -> float:
        if value in (None, ""):
            return 5.0
        try:
            timeout = float(str(value))
        except ValueError as exc:
            msg = "article_resolution_timeout_sec must be a valid number"
            raise ValueError(msg) from exc
        if timeout <= 0:
            msg = "article_resolution_timeout_sec must be greater than 0"
            raise ValueError(msg)
        if timeout > 120:
            msg = "article_resolution_timeout_sec must be 120 seconds or less"
            raise ValueError(msg)
        return timeout

    @model_validator(mode="after")
    def _validate_extraction_tiers(self) -> TwitterConfig:
        if self.force_tier == "firecrawl" and not self.prefer_firecrawl:
            msg = "TWITTER_FORCE_TIER=firecrawl requires TWITTER_PREFER_FIRECRAWL=true"
            raise ValueError(msg)

        if self.force_tier == "playwright" and not self.playwright_enabled:
            msg = "TWITTER_FORCE_TIER=playwright requires TWITTER_PLAYWRIGHT_ENABLED=true"
            raise ValueError(msg)

        if not self.prefer_firecrawl and not self.playwright_enabled:
            msg = (
                "At least one Twitter extraction tier must be enabled "
                "(TWITTER_PREFER_FIRECRAWL or TWITTER_PLAYWRIGHT_ENABLED)."
            )
            raise ValueError(msg)

        return self
