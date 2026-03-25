"""RSS feed polling service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.rss.feed_fetcher import fetch_feed
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.rss_feed_repository import (
    SqliteRSSFeedRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

MAX_FETCH_ERRORS = 10


async def poll_all_feeds(db: DatabaseSessionManager) -> dict:
    """Poll all active RSS feeds for new items."""
    repo = SqliteRSSFeedRepositoryAdapter(db)
    feeds = await repo.async_list_active_feeds()

    new_item_ids: list[int] = []
    stats: dict = {"polled": 0, "new_items": 0, "errors": 0, "skipped": 0}

    for feed in feeds:
        try:
            result = fetch_feed(
                str(feed.get("url") or ""),
                etag=feed.get("etag"),
                last_modified=feed.get("last_modified"),
            )

            if result.not_modified:
                stats["skipped"] += 1
                continue

            # Store new items
            new_count = 0
            for entry in result.entries:
                try:
                    item = await repo.async_create_feed_item(
                        feed_id=int(feed["id"]),
                        guid=entry.guid,
                        title=entry.title,
                        url=entry.url,
                        content=entry.content,
                        author=entry.author,
                        published_at=entry.published_at,
                    )
                    if item is not None:
                        new_count += 1
                        new_item_ids.append(int(item["id"]))
                except Exception:
                    pass

            # Update feed metadata
            await repo.async_update_feed_fetch_success(
                feed_id=int(feed["id"]),
                title=result.title or feed.get("title"),
                description=result.description or feed.get("description"),
                site_url=result.site_url or feed.get("site_url"),
                etag=result.etag,
                last_modified=result.last_modified,
            )

            stats["polled"] += 1
            stats["new_items"] += new_count

        except Exception as exc:
            stats["errors"] += 1
            await repo.async_record_feed_fetch_error(
                feed_id=int(feed["id"]),
                error=str(exc),
                max_fetch_errors=MAX_FETCH_ERRORS,
            )
            logger.warning(
                "rss_feed_poll_error",
                extra={
                    "feed_id": feed.get("id"),
                    "url": feed.get("url"),
                    "error": str(exc)[:200],
                },
            )

    stats["new_item_ids"] = new_item_ids
    logger.info("rss_poll_complete", extra={k: v for k, v in stats.items() if k != "new_item_ids"})
    return stats
