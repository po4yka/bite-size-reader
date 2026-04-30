from __future__ import annotations

import datetime as dt

import pytest

from app.adapters.rss.feed_fetcher import FeedEntry, FeedResult
from app.adapters.rss.signal_ingester import RssSignalIngester
from app.core.time_utils import UTC


@pytest.mark.asyncio
async def test_rss_signal_ingester_normalizes_rss_feed_items() -> None:
    def _fetcher(*_args, **_kwargs):
        return FeedResult(
            title="Example",
            entries=[
                FeedEntry(
                    guid="guid-1",
                    title="Item",
                    url="https://example.com/item",
                    content="body",
                    author="Author",
                    published_at=dt.datetime(2026, 4, 30, tzinfo=UTC),
                )
            ],
            etag="etag",
            last_modified="last",
        )

    result = await RssSignalIngester(
        {"id": 7, "url": "https://example.com/feed.xml"},
        fetcher=_fetcher,
    ).fetch()

    assert result.source.kind == "rss"
    assert result.source.metadata["legacy_rss_feed_id"] == 7
    assert result.items[0].external_id == "guid-1"


@pytest.mark.asyncio
async def test_substack_uses_rss_ingester_contract() -> None:
    def _fetcher(*_args, **_kwargs):
        return FeedResult(title="Platformer", site_url="https://platformer.substack.com")

    result = await RssSignalIngester(
        {"id": 8, "url": "https://platformer.substack.com/feed"},
        fetcher=_fetcher,
    ).fetch()

    assert result.source.kind == "substack"
    assert result.source.external_id == "https://platformer.substack.com/feed"
