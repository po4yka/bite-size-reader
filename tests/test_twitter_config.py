"""Tests for Twitter/X extraction config validation."""

from __future__ import annotations

import pytest

from app.config.twitter import TwitterConfig


def test_twitter_config_defaults_are_valid() -> None:
    cfg = TwitterConfig()
    assert cfg.prefer_firecrawl is True
    assert cfg.article_redirect_resolution_enabled is True
    assert cfg.article_resolution_timeout_sec == 5.0
    assert cfg.force_tier == "auto"
    assert cfg.scraper_profile == "inherit"
    assert cfg.max_concurrent_browsers == 2


def test_twitter_config_requires_at_least_one_extraction_tier() -> None:
    with pytest.raises(ValueError, match="At least one Twitter extraction tier must be enabled"):
        TwitterConfig(prefer_firecrawl=False, playwright_enabled=False)


def test_twitter_config_validates_article_resolution_timeout() -> None:
    with pytest.raises(ValueError, match="article_resolution_timeout_sec must be greater than 0"):
        TwitterConfig(article_resolution_timeout_sec=0)


def test_twitter_force_tier_requires_matching_enabled_tier() -> None:
    with pytest.raises(
        ValueError, match="TWITTER_FORCE_TIER=playwright requires TWITTER_PLAYWRIGHT_ENABLED=true"
    ):
        TwitterConfig(force_tier="playwright", playwright_enabled=False)

    with pytest.raises(
        ValueError, match="TWITTER_FORCE_TIER=firecrawl requires TWITTER_PREFER_FIRECRAWL=true"
    ):
        TwitterConfig(force_tier="firecrawl", prefer_firecrawl=False)
