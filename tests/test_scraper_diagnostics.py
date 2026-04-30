"""Tests for scraper diagnostics payload builder."""

from __future__ import annotations

from app.adapters.content.scraper.diagnostics import build_scraper_diagnostics
from app.config import FirecrawlConfig
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
    assert diagnostics["provider_order_effective"] == [
        "scrapling",
        "firecrawl",
        "playwright",
        "crawlee",
        "direct_html",
    ]


def test_build_scraper_diagnostics_disabled_state() -> None:
    cfg = make_test_app_config(scraper=ScraperConfig(enabled=False))
    diagnostics = build_scraper_diagnostics(cfg)
    assert diagnostics["status"] == "disabled"


def test_firecrawl_diagnostics_report_cloud_mode_when_api_key_configured() -> None:
    cfg = make_test_app_config(
        scraper=ScraperConfig(firecrawl_self_hosted_enabled=False),
        firecrawl=FirecrawlConfig(api_key="fc-test-cloud-key"),
    )

    diagnostics = build_scraper_diagnostics(cfg)
    firecrawl = diagnostics["providers"]["firecrawl"]

    assert firecrawl["enabled"] is True
    assert firecrawl["mode"] == "cloud"
    assert firecrawl["cloud_api_key_configured"] is True
    assert firecrawl["self_hosted_enabled"] is False


def test_firecrawl_diagnostics_report_self_hosted_mode_preference() -> None:
    cfg = make_test_app_config(
        scraper=ScraperConfig(firecrawl_self_hosted_enabled=True),
        firecrawl=FirecrawlConfig(api_key="fc-test-cloud-key"),
    )

    diagnostics = build_scraper_diagnostics(cfg)
    firecrawl = diagnostics["providers"]["firecrawl"]

    assert firecrawl["enabled"] is True
    assert firecrawl["mode"] == "self_hosted"
    assert firecrawl["cloud_api_key_configured"] is True
    assert firecrawl["self_hosted_enabled"] is True


def test_firecrawl_diagnostics_report_disabled_without_any_endpoint() -> None:
    cfg = make_test_app_config(
        scraper=ScraperConfig(firecrawl_self_hosted_enabled=False),
        firecrawl=FirecrawlConfig(api_key=""),
    )

    diagnostics = build_scraper_diagnostics(cfg)
    firecrawl = diagnostics["providers"]["firecrawl"]

    assert firecrawl["enabled"] is False
    assert firecrawl["mode"] == "disabled"
    assert firecrawl["cloud_api_key_configured"] is False
