"""Tier selection policy for Twitter extraction."""

from __future__ import annotations

from typing import Any

from app.config.scraper import profile_timeout_multiplier


class TwitterTierPolicy:
    """Encapsulate Firecrawl/Playwright tier configuration and messaging."""

    def __init__(self, *, cfg: Any) -> None:
        self._cfg = cfg

    def force_tier(self) -> str:
        return str(getattr(self._cfg.twitter, "force_tier", "auto")).strip().lower() or "auto"

    def should_use_firecrawl_tier(self) -> bool:
        if self.force_tier() == "playwright":
            return False
        return bool(getattr(self._cfg.twitter, "prefer_firecrawl", True))

    def should_use_playwright_tier(self) -> bool:
        if self.force_tier() == "firecrawl":
            return False
        return bool(getattr(self._cfg.twitter, "playwright_enabled", False))

    def twitter_profile(self) -> str:
        twitter_profile = (
            str(getattr(self._cfg.twitter, "scraper_profile", "inherit")).strip().lower()
        )
        if twitter_profile == "inherit":
            scraper_cfg = getattr(self._cfg, "scraper", None)
            inherited = str(getattr(scraper_cfg, "profile", "balanced")).strip().lower()
            return inherited or "balanced"
        return twitter_profile or "balanced"

    def effective_timeout_ms(self) -> int:
        multiplier = profile_timeout_multiplier(self.twitter_profile())
        timeout_ms = int(getattr(self._cfg.twitter, "page_timeout_ms", 15_000) * multiplier)
        return max(1_000, timeout_ms)

    def build_extraction_error_message(self) -> str:
        tier_mode = self.force_tier()
        if not self._cfg.twitter.prefer_firecrawl and not self._cfg.twitter.playwright_enabled:
            return (
                "Twitter extraction misconfigured: both Firecrawl and Playwright are disabled. "
                "Enable TWITTER_PREFER_FIRECRAWL or TWITTER_PLAYWRIGHT_ENABLED."
            )
        if tier_mode == "firecrawl":
            return "Twitter content extraction failed (forced Firecrawl tier)"
        if tier_mode == "playwright":
            return "Twitter content extraction failed (forced Playwright tier)"
        if not self._cfg.twitter.playwright_enabled:
            return (
                "Twitter content extraction via Firecrawl returned insufficient content. "
                "Enable TWITTER_PLAYWRIGHT_ENABLED for authenticated extraction."
            )
        return "Twitter content extraction failed (both Firecrawl and Playwright)"
