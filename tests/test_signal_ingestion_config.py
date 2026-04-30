from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.signal_ingestion import SignalIngestionConfig


def test_signal_ingestion_defaults_keep_optional_sources_disabled() -> None:
    cfg = SignalIngestionConfig()

    assert cfg.enabled is False
    assert cfg.any_enabled is False
    assert cfg.hn_feed_names() == ("top",)
    assert cfg.reddit_names() == ()
    assert cfg.twitter_ack_cost is False


def test_signal_ingestion_parses_yaml_style_lists() -> None:
    cfg = SignalIngestionConfig(
        enabled=True,
        hn_enabled=True,
        hn_feeds=["top", "new"],
        reddit_enabled=True,
        reddit_subreddits=["r/selfhosted", "python"],
    )

    assert cfg.any_enabled is True
    assert cfg.hn_feed_names() == ("top", "new")
    assert cfg.reddit_names() == ("selfhosted", "python")


def test_reddit_free_tier_guard_caps_requests_per_minute() -> None:
    with pytest.raises(ValidationError):
        SignalIngestionConfig(reddit_requests_per_minute=101)
