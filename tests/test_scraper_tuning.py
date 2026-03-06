"""Tests for scraper runtime tuning helpers."""

from __future__ import annotations

from app.adapters.content.scraper.runtime_tuning import (
    profile_retry_budget,
    profile_timeout_multiplier,
    tuned_firecrawl_wait_for_ms,
    tuned_provider_timeout,
)


def test_profile_timeout_multiplier_values() -> None:
    assert profile_timeout_multiplier("fast") == 0.75
    assert profile_timeout_multiplier("balanced") == 1.0
    assert profile_timeout_multiplier("robust") == 1.35


def test_profile_retry_budget_rules() -> None:
    assert profile_retry_budget(4, "fast") == 1
    assert profile_retry_budget(3, "balanced") == 3
    assert profile_retry_budget(4, "robust") == 5


def test_js_heavy_timeout_overlay_for_scrapling() -> None:
    timeout = tuned_provider_timeout(
        base_timeout_sec=30,
        profile="balanced",
        provider="scrapling",
        url="https://news.example.com/article",
        js_heavy_hosts=("example.com",),
    )
    assert timeout == 24.0


def test_js_heavy_timeout_overlay_for_playwright() -> None:
    timeout = tuned_provider_timeout(
        base_timeout_sec=30,
        profile="balanced",
        provider="playwright",
        url="https://app.example.com/dashboard",
        js_heavy_hosts=("example.com",),
    )
    assert timeout == 37.5


def test_firecrawl_wait_for_overlay_capped() -> None:
    wait_for_ms = tuned_firecrawl_wait_for_ms(
        base_wait_for_ms=9000,
        url="https://app.example.com/dashboard",
        js_heavy_hosts=("example.com",),
    )
    assert wait_for_ms == 10000
