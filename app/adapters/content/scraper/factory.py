"""Factory for creating ContentScraperChain from application config."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.content.scraper.chain import ContentScraperChain

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.scraper.protocol import ContentScraperProtocol
    from app.config import AppConfig

logger = logging.getLogger(__name__)


class ContentScraperFactory:
    @staticmethod
    def create_from_config(
        cfg: AppConfig,
        audit: Callable[[str, str, dict], None] | None = None,
    ) -> ContentScraperChain:
        """Build a scraper chain from config, respecting provider_order."""
        providers: list[ContentScraperProtocol] = []
        scraper_cfg = cfg.scraper

        builder_map = {
            "scrapling": lambda: _build_scrapling(scraper_cfg),
            "firecrawl": lambda: _build_firecrawl(cfg, audit),
            "direct_html": lambda: _build_direct_html(scraper_cfg),
        }

        for name in scraper_cfg.provider_order:
            builder = builder_map.get(name)
            if builder is None:
                logger.warning("scraper_unknown_provider", extra={"provider": name})
                continue
            provider = builder()
            if provider is not None:
                providers.append(provider)
                logger.info("scraper_provider_registered", extra={"provider": name})

        if not providers:
            logger.warning("scraper_no_providers_configured_using_direct_html")
            from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

            providers.append(DirectHTMLProvider())

        return ContentScraperChain(providers, audit=audit)


def _build_scrapling(scraper_cfg: object) -> ContentScraperProtocol | None:
    if not getattr(scraper_cfg, "scrapling_enabled", True):
        return None
    try:
        from app.adapters.content.scraper.scrapling_provider import ScraplingProvider

        return ScraplingProvider(
            timeout_sec=getattr(scraper_cfg, "scrapling_timeout_sec", 30),
            stealth_fallback=getattr(scraper_cfg, "scrapling_stealth_fallback", True),
        )
    except Exception as exc:
        logger.warning(
            "scrapling_provider_init_failed",
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
        from app.adapters.external.firecrawl.client import FirecrawlClient

        from .firecrawl_provider import FirecrawlProvider

        client = FirecrawlClient(
            api_key=scraper_cfg.firecrawl_self_hosted_api_key,
            timeout_sec=cfg.firecrawl.timeout_sec,
            audit=audit,
            debug_payloads=cfg.runtime.debug_payloads,
            max_connections=cfg.firecrawl.max_connections,
            max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
            keepalive_expiry=cfg.firecrawl.keepalive_expiry,
            max_response_size_mb=cfg.firecrawl.max_response_size_mb,
            base_url=scraper_cfg.firecrawl_self_hosted_url,
        )
        return FirecrawlProvider(client, name="firecrawl_self_hosted")
    except Exception as exc:
        logger.warning(
            "firecrawl_self_hosted_init_failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


def _build_direct_html(scraper_cfg: object) -> ContentScraperProtocol | None:
    from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

    return DirectHTMLProvider(
        timeout_sec=getattr(scraper_cfg, "scrapling_timeout_sec", 30),
    )
