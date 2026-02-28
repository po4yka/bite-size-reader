"""Tests for Twitter/X extraction config validation."""

from __future__ import annotations

import pytest

from app.config.twitter import TwitterConfig


def test_twitter_config_defaults_are_valid() -> None:
    cfg = TwitterConfig()
    assert cfg.prefer_firecrawl is True


def test_twitter_config_requires_at_least_one_extraction_tier() -> None:
    with pytest.raises(ValueError, match="At least one Twitter extraction tier must be enabled"):
        TwitterConfig(prefer_firecrawl=False, playwright_enabled=False)
