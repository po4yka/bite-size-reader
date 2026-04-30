"""RSS feed polling service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.rss.feed_fetcher import fetch_feed
from app.adapters.rss.signal_ingester import RssSignalIngester
from app.adapters.rss.substack import is_substack_url
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.rss_feed_repository import (
    SqliteRSSFeedRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.signal_source_repository import (
    SqliteSignalSourceRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

MAX_FETCH_ERRORS = 10
SIGNAL_SOURCE_BASE_BACKOFF_SECONDS = 300


async def poll_all_feeds(db: DatabaseSessionManager) -> dict:
    """Poll all active RSS feeds for new items."""
    repo = SqliteRSSFeedRepositoryAdapter(db)
    signal_repo = SqliteSignalSourceRepositoryAdapter(db)
    feeds = await repo.async_list_active_feeds()

    new_item_ids: list[int] = []
    stats: dict = {"polled": 0, "new_items": 0, "errors": 0, "skipped": 0}

    for feed in feeds:
        signal_source: dict | None = None
        try:
            feed_url = str(feed.get("url") or "")
            signal_source = await signal_repo.async_upsert_source(
                kind="substack" if is_substack_url(feed_url) else "rss",
                external_id=feed_url,
                url=feed.get("url"),
                title=feed.get("title"),
                description=feed.get("description"),
                site_url=feed.get("site_url"),
                metadata={
                    "etag": feed.get("etag"),
                    "last_modified": feed.get("last_modified"),
                    "legacy_rss_feed_id": feed.get("id"),
                },
            )
            ingester = RssSignalIngester(feed, fetcher=fetch_feed)
            result = await ingester.fetch()
            signal_source = await signal_repo.async_upsert_source(
                kind=result.source.kind,
                external_id=result.source.external_id,
                url=result.source.url,
                title=result.source.title,
                description=result.source.description,
                site_url=result.source.site_url,
                metadata=result.source.metadata,
            )

            if result.not_modified:
                stats["skipped"] += 1
                await signal_repo.async_record_source_fetch_success(int(signal_source["id"]))
                continue

            # Store new items
            new_count = 0
            for item_result in result.items:
                try:
                    item = await repo.async_create_feed_item(
                        feed_id=int(feed["id"]),
                        guid=item_result.external_id,
                        title=item_result.title,
                        url=item_result.canonical_url,
                        content=item_result.content_text,
                        author=item_result.author,
                        published_at=item_result.published_at,
                    )
                    if item is not None:
                        new_count += 1
                        new_item_ids.append(int(item["id"]))
                        await signal_repo.async_upsert_feed_item(
                            source_id=int(signal_source["id"]),
                            external_id=item_result.external_id,
                            canonical_url=item_result.canonical_url,
                            title=item_result.title,
                            content_text=item_result.content_text,
                            author=item_result.author,
                            published_at=item_result.published_at,
                            engagement=item_result.engagement,
                            metadata={**item_result.metadata, "legacy_rss_item_id": item["id"]},
                        )
                        targets = await repo.async_list_delivery_targets([int(item["id"])])
                        for target in targets:
                            for subscriber_id in target.get("subscriber_ids", []):
                                await signal_repo.async_subscribe(
                                    user_id=int(subscriber_id),
                                    source_id=int(signal_source["id"]),
                                )
                except Exception:
                    logger.warning(
                        "rss_item_create_failed",
                        extra={"feed_id": feed["id"], "guid": item_result.external_id},
                        exc_info=True,
                    )

            # Update feed metadata
            await repo.async_update_feed_fetch_success(
                feed_id=int(feed["id"]),
                title=result.source.title,
                description=result.source.description,
                site_url=result.source.site_url,
                etag=result.source.metadata.get("etag"),
                last_modified=result.source.metadata.get("last_modified"),
            )
            await signal_repo.async_record_source_fetch_success(int(signal_source["id"]))

            stats["polled"] += 1
            stats["new_items"] += new_count

        except Exception as exc:
            stats["errors"] += 1
            await repo.async_record_feed_fetch_error(
                feed_id=int(feed["id"]),
                error=str(exc),
                max_fetch_errors=MAX_FETCH_ERRORS,
            )
            if signal_source is not None:
                await signal_repo.async_record_source_fetch_error(
                    source_id=int(signal_source["id"]),
                    error=str(exc),
                    max_errors=MAX_FETCH_ERRORS,
                    base_backoff_seconds=SIGNAL_SOURCE_BASE_BACKOFF_SECONDS,
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
