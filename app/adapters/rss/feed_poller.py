"""RSS feed polling service."""

from __future__ import annotations

from app.adapters.rss.feed_fetcher import fetch_feed
from app.core.logging_utils import get_logger
from app.db.models import RSSFeed, RSSFeedItem, RSSFeedSubscription

logger = get_logger(__name__)

MAX_FETCH_ERRORS = 10


async def poll_all_feeds() -> dict:
    """Poll all active RSS feeds for new items."""
    # Query feeds that have at least one active subscription
    feeds = list(
        RSSFeed.select()
        .join(RSSFeedSubscription)
        .where((RSSFeed.is_active == True) & (RSSFeedSubscription.is_active == True))  # noqa: E712
        .distinct()
    )

    new_item_ids: list[int] = []
    stats: dict = {"polled": 0, "new_items": 0, "errors": 0, "skipped": 0}

    for feed in feeds:
        try:
            result = fetch_feed(
                feed.url,
                etag=feed.etag,
                last_modified=feed.last_modified,
            )

            if result.not_modified:
                stats["skipped"] += 1
                continue

            # Store new items
            new_count = 0
            for entry in result.entries:
                try:
                    item, created = RSSFeedItem.get_or_create(
                        feed=feed.id,
                        guid=entry.guid,
                        defaults={
                            "title": entry.title,
                            "url": entry.url,
                            "content": entry.content,
                            "author": entry.author,
                            "published_at": entry.published_at,
                        },
                    )
                    if created:
                        new_count += 1
                        new_item_ids.append(item.id)
                except Exception:
                    pass

            # Update feed metadata
            from datetime import datetime

            from app.core.time_utils import UTC

            now = datetime.now(UTC)
            RSSFeed.update(
                title=result.title or feed.title,
                description=result.description or feed.description,
                site_url=result.site_url or feed.site_url,
                last_fetched_at=now,
                last_successful_at=now,
                etag=result.etag,
                last_modified=result.last_modified,
                fetch_error_count=0,
                last_error=None,
            ).where(RSSFeed.id == feed.id).execute()

            stats["polled"] += 1
            stats["new_items"] += new_count

        except Exception as exc:
            stats["errors"] += 1
            error_count = feed.fetch_error_count + 1
            update_fields = {
                RSSFeed.fetch_error_count: error_count,
                RSSFeed.last_error: str(exc)[:500],
            }
            if error_count >= MAX_FETCH_ERRORS:
                update_fields[RSSFeed.is_active] = False
            RSSFeed.update(update_fields).where(RSSFeed.id == feed.id).execute()
            logger.warning(
                "rss_feed_poll_error",
                extra={
                    "feed_id": feed.id,
                    "url": feed.url,
                    "error": str(exc)[:200],
                },
            )

    stats["new_item_ids"] = new_item_ids
    logger.info("rss_poll_complete", extra={k: v for k, v in stats.items() if k != "new_item_ids"})
    return stats
