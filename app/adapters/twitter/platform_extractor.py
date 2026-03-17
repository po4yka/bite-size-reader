"""Platform extractor for Twitter/X URLs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.content.platform_extraction.protocol import PlatformExtractor
from app.adapters.twitter.extraction_coordinator import TwitterExtractionCoordinator
from app.adapters.twitter.firecrawl_extractor import TwitterFirecrawlExtractor
from app.adapters.twitter.playwright_extractor import TwitterPlaywrightExtractor
from app.adapters.twitter.tier_policy import TwitterTierPolicy
from app.core.url_utils import is_twitter_url

if TYPE_CHECKING:
    from app.adapters.content.platform_extraction.lifecycle import PlatformRequestLifecycle
    from app.adapters.content.platform_extraction.models import (
        PlatformExtractionRequest,
        PlatformExtractionResult,
    )
    from app.adapters.external.response_formatter import ResponseFormatter


class TwitterPlatformExtractor(PlatformExtractor):
    """Platform extractor for Twitter/X content."""

    def __init__(
        self,
        *,
        cfg: Any,
        db: Any,
        firecrawl: Any,
        response_formatter: ResponseFormatter,
        message_persistence: Any,
        firecrawl_sem: Any,
        schedule_crawl_persistence: Any,
        lifecycle: PlatformRequestLifecycle,
    ) -> None:
        _ = db
        request_repo = message_persistence.request_repo
        tier_policy = TwitterTierPolicy(cfg=cfg)
        firecrawl_extractor = TwitterFirecrawlExtractor(
            firecrawl=firecrawl,
            firecrawl_sem=firecrawl_sem,
            schedule_crawl_persistence=schedule_crawl_persistence,
            request_repo=request_repo,
        )
        playwright_extractor = TwitterPlaywrightExtractor(
            cfg=cfg,
            request_repo=request_repo,
        )
        self._coordinator = TwitterExtractionCoordinator(
            cfg=cfg,
            response_formatter=response_formatter,
            request_repo=request_repo,
            lifecycle=lifecycle,
            tier_policy=tier_policy,
            firecrawl_extractor=firecrawl_extractor,
            playwright_extractor=playwright_extractor,
        )

    def supports(self, normalized_url: str) -> bool:
        return is_twitter_url(normalized_url)

    async def extract(self, request: PlatformExtractionRequest) -> PlatformExtractionResult:
        return await self._coordinator.extract(request)
