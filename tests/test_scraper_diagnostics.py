"""Tests for scraper diagnostics payload builder."""

from __future__ import annotations

from app.adapters.content.scraper.diagnostics import build_scraper_diagnostics
from app.config.scraper import ScraperConfig
from app.config.twitter import TwitterConfig

from .conftest import make_test_app_config


def test_build_scraper_diagnostics_includes_expected_keys() -> None:
    cfg = make_test_app_config(
        scraper=ScraperConfig(),
        twitter=TwitterConfig(),
    )

    diagnostics = build_scraper_diagnostics(cfg)

    assert diagnostics["status"] in {"healthy", "degraded", "disabled"}
    assert "provider_order_effective" in diagnostics
    assert "providers" in diagnostics
    assert "twitter" in diagnostics
    assert "scrapling" in diagnostics["providers"]
    assert "direct_html" in diagnostics["providers"]


def test_build_scraper_diagnostics_disabled_state() -> None:
    cfg = make_test_app_config(scraper=ScraperConfig(enabled=False))
    diagnostics = build_scraper_diagnostics(cfg)
    assert diagnostics["status"] == "disabled"
