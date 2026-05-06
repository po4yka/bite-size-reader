"""RSS feed item delivery service -- summarize and send new items to subscribers."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from app.core.content_cleaner import clean_content_for_llm
from app.core.lang import detect_language
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.content.pure_summary_service import PureSummaryService
    from app.adapters.content.scraper.chain import ContentScraperChain
    from app.config.rss import RSSConfig
    from app.infrastructure.persistence.repositories.rss_feed_repository import (
        SqliteRSSFeedRepositoryAdapter,
    )

logger = get_logger(__name__)


def _format_rss_summary(
    summary: dict[str, Any], item_title: str | None, item_url: str | None
) -> str:
    """Build a Telegram-friendly text from a summary dict and RSS item metadata."""
    parts: list[str] = []

    if item_title:
        parts.append(f"**{item_title}**")

    tldr = summary.get("tldr")
    if tldr:
        parts.append(f"\n{tldr}")

    summary_250 = summary.get("summary_250")
    if summary_250:
        parts.append(f"\n{summary_250}")

    key_ideas = summary.get("key_ideas")
    if isinstance(key_ideas, list) and key_ideas:
        ideas_text = "\n".join(f"- {idea}" for idea in key_ideas[:5])
        parts.append(f"\nKey ideas:\n{ideas_text}")

    tags = summary.get("topic_tags")
    if isinstance(tags, list) and tags:
        parts.append("\n" + " ".join(f"#{tag}" for tag in tags[:5]))

    if item_url:
        parts.append(f"\n[Read original]({item_url})")

    return "\n".join(parts)


class RSSDeliveryService:
    """Summarize and deliver new RSS feed items to subscribed users."""

    def __init__(
        self,
        *,
        cfg: RSSConfig,
        pure_summary_service: PureSummaryService,
        system_prompt_loader: Callable[[str], str],
        rss_repository: SqliteRSSFeedRepositoryAdapter,
        scraper_chain: ContentScraperChain | None = None,
    ) -> None:
        self._cfg = cfg
        self._pure = pure_summary_service
        self._load_prompt = system_prompt_loader
        self._rss_repo = rss_repository
        self._scraper_chain = scraper_chain

    async def deliver_new_items(
        self,
        send_func: Callable[[int, str], Awaitable[None]],
        new_item_ids: list[int] | None = None,
    ) -> dict[str, int]:
        """Summarize and deliver undelivered RSS items to their subscribers.

        Args:
            send_func: async callback ``(user_id, text) -> None`` for Telegram delivery.
            new_item_ids: optional whitelist of item IDs to process (from poll_all_feeds).
                          If None, scans for all undelivered items.

        Returns:
            Stats dict with ``delivered``, ``errors``, ``skipped`` counts.
        """
        stats = {"delivered": 0, "errors": 0, "skipped": 0}
        sem = asyncio.Semaphore(self._cfg.concurrency)

        # Find items that need delivery
        items = await self._query_undelivered_items(new_item_ids)
        if not items:
            return stats

        # Cap per cycle
        items = items[: self._cfg.max_items_per_poll]

        for item in items:
            subscriber_ids = list(item.get("subscriber_ids") or [])
            for user_id in subscriber_ids:
                try:
                    await self._deliver_one(item, user_id, send_func, sem)
                    stats["delivered"] += 1
                except Exception:
                    logger.exception(
                        "rss_delivery_item_failed",
                        extra={"item_id": item.get("id"), "user_id": user_id},
                    )
                    stats["errors"] += 1

        logger.info("rss_delivery_complete", extra=stats)
        return stats

    async def _query_undelivered_items(
        self,
        new_item_ids: list[int] | None,
    ) -> list[dict[str, Any]]:
        """Return (item, [subscriber_user_ids]) pairs that haven't been delivered yet."""
        return await self._rss_repo.async_list_delivery_targets(new_item_ids)

    async def _deliver_one(
        self,
        item: dict[str, Any],
        user_id: int,
        send_func: Callable[[int, str], Awaitable[None]],
        sem: asyncio.Semaphore,
    ) -> None:
        """Summarize a single RSS item and deliver to one user."""
        correlation_id = f"rss_{uuid.uuid4().hex[:12]}"
        content = str(item.get("content") or "")

        if len(content) < self._cfg.min_content_length:
            if not item.get("url"):
                logger.info(
                    "rss_delivery_skip_no_content",
                    extra={"item_id": item.get("id"), "cid": correlation_id},
                )
                await self._rss_repo.async_mark_item_delivered(
                    user_id=user_id, item_id=int(item["id"])
                )
                return
            scraped_content = await self._try_scrape_url(item["url"], correlation_id)
            if scraped_content and len(scraped_content) >= self._cfg.min_content_length:
                content = scraped_content
            else:
                logger.info(
                    "rss_delivery_skip_short_content",
                    extra={
                        "item_id": item.get("id"),
                        "content_len": len(content),
                        "scraped": scraped_content is not None,
                        "cid": correlation_id,
                    },
                )
                await self._rss_repo.async_mark_item_delivered(
                    user_id=user_id, item_id=int(item["id"])
                )
                return

        cleaned = clean_content_for_llm(content)
        lang = detect_language(cleaned)
        system_prompt = self._load_prompt(lang)

        from app.adapters.content.summarization_models import PureSummaryRequest

        request = PureSummaryRequest(
            content_text=cleaned,
            chosen_lang=lang,
            system_prompt=system_prompt,
            correlation_id=correlation_id,
        )

        async with sem:
            summary = await self._pure.summarize(request)

        text = _format_rss_summary(summary, item.get("title"), item.get("url"))
        await send_func(user_id, text)

        await self._rss_repo.async_mark_item_delivered(user_id=user_id, item_id=int(item["id"]))
        logger.info(
            "rss_delivery_sent",
            extra={
                "item_id": item.get("id"),
                "user_id": user_id,
                "cid": correlation_id,
            },
        )

    async def _try_scrape_url(self, url: str, correlation_id: str) -> str | None:
        """Attempt to scrape full article content when RSS inline content is too short.

        Returns scraped markdown text on success, None on failure or if disabled.
        """
        if not self._cfg.scrape_short_content or self._scraper_chain is None:
            return None

        try:
            from app.core.call_status import CallStatus

            result = await self._scraper_chain.scrape_markdown(url)
            if result.status == CallStatus.OK and result.content_markdown:
                logger.info(
                    "rss_scrape_success",
                    extra={
                        "url": url,
                        "content_len": len(result.content_markdown),
                        "cid": correlation_id,
                    },
                )
                return result.content_markdown
        except Exception:
            logger.warning(
                "rss_scrape_failed",
                extra={"url": url, "cid": correlation_id},
                exc_info=True,
            )
        return None
