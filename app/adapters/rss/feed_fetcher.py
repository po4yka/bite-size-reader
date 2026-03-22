"""RSS/Atom feed fetcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app.core.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class FeedEntry:
    guid: str
    title: str | None = None
    url: str | None = None
    content: str | None = None
    author: str | None = None
    published_at: datetime | None = None


@dataclass
class FeedResult:
    title: str | None = None
    description: str | None = None
    site_url: str | None = None
    entries: list[FeedEntry] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


def fetch_feed(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: float = 30.0,
) -> FeedResult:
    """Fetch and parse an RSS/Atom feed.

    Uses conditional headers (ETag, Last-Modified) to avoid re-downloading unchanged feeds.
    Returns FeedResult with not_modified=True if server returns 304.
    """
    headers: dict[str, str] = {"User-Agent": "BSR-FeedFetcher/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

    if resp.status_code == 304:
        return FeedResult(not_modified=True)

    resp.raise_for_status()

    import feedparser

    parsed = feedparser.parse(resp.content)

    entries = []
    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("link") or entry.get("title", "")
        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                import time

                pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=UTC)
            except (ValueError, OverflowError, TypeError):
                pass

        content_text = ""
        if entry.get("content"):
            content_text = entry.content[0].get("value", "")
        elif entry.get("summary"):
            content_text = entry.summary

        entries.append(
            FeedEntry(
                guid=guid,
                title=entry.get("title"),
                url=entry.get("link"),
                content=content_text or None,
                author=entry.get("author"),
                published_at=pub_date,
            )
        )

    feed_info = parsed.feed
    return FeedResult(
        title=feed_info.get("title"),
        description=feed_info.get("subtitle") or feed_info.get("description"),
        site_url=feed_info.get("link"),
        entries=entries,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
    )
