"""Factory for creating ContentScraperChain from application config."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.content.scraper.chain import ContentScraperChain
from app.adapters.content.scraper.diagnostics import build_scraper_diagnostics
from app.config.scraper import profile_retry_budget, profile_timeout_multiplier

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.scraper.protocol import ContentScraperProtocol
    from app.config import AppConfig

logger = logging.getLogger(__name__)

_BROWSER_PROVIDERS = {"playwright", "crawlee"}


class ContentScraperFactory:
    @staticmethod
    def create_from_config(
        cfg: AppConfig,
        audit: Callable[[str, str, dict], None] | None = None,
    ) -> ContentScraperChain:
        """Build a scraper chain from config, respecting provider_order."""
        scraper_cfg = cfg.scraper

        diagnostics = build_scraper_diagnostics(cfg)
        logger.info("scraper_config_effective", extra={"scraper": diagnostics})

        if not scraper_cfg.enabled:
            from app.adapters.content.scraper.disabled_provider import DisabledScraperProvider

            disabled_provider = DisabledScraperProvider(
                reason="Scraper disabled by SCRAPER_ENABLED=false",
            )
            return ContentScraperChain([disabled_provider], audit=audit)

        providers: list[ContentScraperProtocol] = []

        provider_order = (
            [scraper_cfg.force_provider]
            if scraper_cfg.force_provider
            else list(scraper_cfg.provider_order)
        )

        builder_map = {
            "scrapling": lambda: _build_scrapling(scraper_cfg),
            "defuddle": lambda: _build_defuddle(scraper_cfg),
            "firecrawl": lambda: _build_firecrawl(cfg, audit),
            "playwright": lambda: _build_playwright(scraper_cfg),
            "crawlee": lambda: _build_crawlee(scraper_cfg),
            "direct_html": lambda: _build_direct_html(scraper_cfg),
        }

        for name in provider_order:
            if not scraper_cfg.browser_enabled and name in _BROWSER_PROVIDERS:
                logger.info(
                    "scraper_provider_skipped_browser_disabled",
                    extra={"provider": name},
                )
                continue

            builder = builder_map.get(name)
            if builder is None:
                logger.warning("scraper_unknown_provider", extra={"provider": name})
                continue

            provider = builder()
            if provider is not None:
                providers.append(provider)
                logger.info("scraper_provider_registered", extra={"provider": name})

        if scraper_cfg.force_provider and not providers:
            msg = (
                f"SCRAPER_FORCE_PROVIDER='{scraper_cfg.force_provider}' is unavailable or disabled"
            )
            raise RuntimeError(msg)

        if not providers:
            logger.warning("scraper_no_providers_configured")
            fallback_provider = _build_direct_html(scraper_cfg)
            if fallback_provider is not None:
                providers.append(fallback_provider)
            else:
                from app.adapters.content.scraper.disabled_provider import DisabledScraperProvider

                providers.append(
                    DisabledScraperProvider(
                        reason="No scraper providers are available from configuration"
                    )
                )

        return ContentScraperChain(providers, audit=audit)


def _build_scrapling(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "scrapling_enabled", True):
        return None
    try:
        from app.adapters.content.scraper.scrapling_provider import ScraplingProvider

        return ScraplingProvider(
            timeout_sec=getattr(scraper_cfg, "scrapling_timeout_sec", 30),
            stealth_fallback=getattr(scraper_cfg, "scrapling_stealth_fallback", True),
            min_content_length=getattr(scraper_cfg, "min_content_length", 400),
            profile=getattr(scraper_cfg, "profile", "balanced"),
            js_heavy_hosts=getattr(scraper_cfg, "js_heavy_hosts", ()),
        )
    except Exception as exc:
        logger.warning(
            "scrapling_provider_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


def _build_defuddle(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "defuddle_enabled", True):
        return None
    try:
        from app.adapters.content.scraper.defuddle_provider import DefuddleProvider

        timeout_multiplier = profile_timeout_multiplier(getattr(scraper_cfg, "profile", "balanced"))
        timeout_sec = max(
            1,
            round(getattr(scraper_cfg, "defuddle_timeout_sec", 20) * timeout_multiplier),
        )
        return DefuddleProvider(
            timeout_sec=timeout_sec,
            min_content_length=getattr(scraper_cfg, "min_content_length", 400),
            api_base_url=getattr(scraper_cfg, "defuddle_api_base_url", "https://defuddle.md"),
        )
    except Exception as exc:
        logger.warning(
            "defuddle_provider_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


def _build_firecrawl(
    cfg: AppConfig,
    audit: Callable[[str, str, dict], None] | None,
) -> ContentScraperProtocol | None:
    scraper_cfg = cfg.scraper
    if not getattr(scraper_cfg, "firecrawl_self_hosted_enabled", False):
        return None
    try:
        from app.adapters.external.firecrawl.client import FirecrawlClient, FirecrawlClientConfig

        from .firecrawl_provider import FirecrawlProvider

        profile = getattr(scraper_cfg, "profile", "balanced")
        timeout_multiplier = profile_timeout_multiplier(profile)
        profiled_timeout = max(
            1, round(getattr(scraper_cfg, "firecrawl_timeout_sec", 90) * timeout_multiplier)
        )
        profiled_retries = profile_retry_budget(
            getattr(scraper_cfg, "firecrawl_max_retries", 3),
            profile,
        )

        client_cfg = FirecrawlClientConfig(
            timeout_sec=profiled_timeout,
            max_retries=profiled_retries,
            backoff_base=cfg.firecrawl.retry_initial_delay,
            debug_payloads=cfg.runtime.debug_payloads,
            max_connections=getattr(scraper_cfg, "firecrawl_max_connections", 10),
            max_keepalive_connections=getattr(
                scraper_cfg, "firecrawl_max_keepalive_connections", 5
            ),
            keepalive_expiry=getattr(scraper_cfg, "firecrawl_keepalive_expiry", 30.0),
            max_response_size_mb=getattr(scraper_cfg, "firecrawl_max_response_size_mb", 50),
            max_age_seconds=cfg.firecrawl.max_age_seconds,
            remove_base64_images=cfg.firecrawl.remove_base64_images,
            block_ads=cfg.firecrawl.block_ads,
            skip_tls_verification=cfg.firecrawl.skip_tls_verification,
            include_markdown_format=cfg.firecrawl.include_markdown_format,
            include_html_format=cfg.firecrawl.include_html_format,
            include_links_format=cfg.firecrawl.include_links_format,
            include_summary_format=cfg.firecrawl.include_summary_format,
            include_images_format=cfg.firecrawl.include_images_format,
            enable_screenshot_format=cfg.firecrawl.enable_screenshot_format,
            screenshot_full_page=cfg.firecrawl.screenshot_full_page,
            screenshot_quality=cfg.firecrawl.screenshot_quality,
            screenshot_viewport_width=cfg.firecrawl.screenshot_viewport_width,
            screenshot_viewport_height=cfg.firecrawl.screenshot_viewport_height,
            json_prompt=cfg.firecrawl.json_prompt,
            json_schema=cfg.firecrawl.json_schema or {},
            wait_for_ms=getattr(scraper_cfg, "firecrawl_wait_for_ms", 3000),
        )
        client = FirecrawlClient(
            scraper_cfg.firecrawl_self_hosted_api_key,
            client_cfg,
            audit=audit,
            base_url=scraper_cfg.firecrawl_self_hosted_url,
        )
        return FirecrawlProvider(
            client,
            name="firecrawl_self_hosted",
            wait_for_ms=getattr(scraper_cfg, "firecrawl_wait_for_ms", 3000),
            js_heavy_hosts=getattr(scraper_cfg, "js_heavy_hosts", ()),
        )
    except Exception as exc:
        logger.warning(
            "firecrawl_self_hosted_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


def _build_direct_html(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "direct_html_enabled", True):
        return None

    from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

    timeout_multiplier = profile_timeout_multiplier(getattr(scraper_cfg, "profile", "balanced"))
    timeout_sec = max(
        1,
        round(getattr(scraper_cfg, "direct_html_timeout_sec", 30) * timeout_multiplier),
    )

    return DirectHTMLProvider(
        timeout_sec=timeout_sec,
        min_text_length=getattr(scraper_cfg, "min_content_length", 400),
        max_response_mb=getattr(scraper_cfg, "direct_html_max_response_mb", 10),
    )


def _build_playwright(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "playwright_enabled", True):
        return None
    try:
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        return PlaywrightProvider(
            timeout_sec=getattr(scraper_cfg, "playwright_timeout_sec", 30),
            headless=getattr(scraper_cfg, "playwright_headless", True),
            min_text_length=getattr(scraper_cfg, "min_content_length", 400),
            profile=getattr(scraper_cfg, "profile", "balanced"),
            js_heavy_hosts=getattr(scraper_cfg, "js_heavy_hosts", ()),
        )
    except Exception as exc:
        logger.warning(
            "playwright_provider_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


def _build_crawlee(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "crawlee_enabled", True):
        return None
    try:
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        profile = getattr(scraper_cfg, "profile", "balanced")
        profiled_retries = profile_retry_budget(
            getattr(scraper_cfg, "crawlee_max_retries", 2),
            profile,
        )
        return CrawleeProvider(
            timeout_sec=getattr(scraper_cfg, "crawlee_timeout_sec", 45),
            headless=getattr(scraper_cfg, "crawlee_headless", True),
            max_retries=profiled_retries,
            min_content_length=getattr(scraper_cfg, "min_content_length", 400),
            profile=profile,
            js_heavy_hosts=getattr(scraper_cfg, "js_heavy_hosts", ()),
        )
    except Exception as exc:
        logger.warning(
            "crawlee_provider_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None
