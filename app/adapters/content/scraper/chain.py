"""Ordered fallback chain implementing ContentScraperProtocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.external.firecrawl.models import FirecrawlResult
from app.core.call_status import CallStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.scraper.protocol import ContentScraperProtocol

logger = logging.getLogger(__name__)


class ContentScraperChain:
    """Try each provider in order, return the first successful result."""

    def __init__(
        self,
        providers: list[ContentScraperProtocol],
        audit: Callable[[str, str, dict], None] | None = None,
    ) -> None:
        if not providers:
            msg = "ContentScraperChain requires at least one provider"
            raise ValueError(msg)
        self._providers = providers
        self._audit = audit

    @property
    def providers(self) -> list[ContentScraperProtocol]:
        """Read-only view of the provider list."""
        return list(self._providers)

    @property
    def provider_name(self) -> str:
        return "chain"

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        last_result: FirecrawlResult | None = None
        errors: list[str] = []

        for provider in self._providers:
            name = provider.provider_name
            try:
                result = await provider.scrape_markdown(url, mobile=mobile, request_id=request_id)
            except Exception as exc:
                error_msg = f"{name}: {exc}"
                errors.append(error_msg)
                logger.warning(
                    "scraper_chain_provider_exception",
                    extra={
                        "provider": name,
                        "url": url,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "request_id": request_id,
                    },
                )
                continue

            has_content = result.status == CallStatus.OK and (
                bool(result.content_markdown and result.content_markdown.strip())
                or bool(result.content_html and result.content_html.strip())
            )

            if has_content:
                logger.info(
                    "scraper_chain_success",
                    extra={
                        "provider": name,
                        "url": url,
                        "latency_ms": result.latency_ms,
                        "request_id": request_id,
                        "tried": len(errors) + 1,
                    },
                )
                if self._audit:
                    self._audit(
                        "INFO",
                        "scraper_chain_success",
                        {
                            "provider": name,
                            "url": url,
                            "latency_ms": result.latency_ms,
                            "request_id": request_id,
                        },
                    )
                return result

            error_msg = f"{name}: {result.error_text or 'no content'}"
            errors.append(error_msg)
            last_result = result
            logger.info(
                "scraper_chain_provider_failed",
                extra={
                    "provider": name,
                    "url": url,
                    "error": result.error_text,
                    "request_id": request_id,
                },
            )

        # All providers failed
        logger.warning(
            "scraper_chain_exhausted",
            extra={
                "url": url,
                "providers_tried": len(errors),
                "errors": errors,
                "request_id": request_id,
            },
        )

        if last_result is not None:
            return last_result

        return FirecrawlResult(
            status=CallStatus.ERROR,
            error_text=f"All providers failed: {'; '.join(errors)}",
            source_url=url,
            endpoint="chain",
        )

    async def aclose(self) -> None:
        for provider in self._providers:
            try:
                await provider.aclose()
            except Exception as exc:
                logger.debug(
                    "scraper_chain_close_error",
                    extra={
                        "provider": provider.provider_name,
                        "error": str(exc),
                    },
                )
