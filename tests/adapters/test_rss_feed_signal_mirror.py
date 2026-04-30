"""RSS poller integration with generic signal sources."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.adapters.rss.feed_fetcher import FeedEntry, FeedResult
from app.core.time_utils import UTC


class _FakeRSSRepo:
    def __init__(self, _db) -> None:
        self.items: list[dict] = []

    async def async_list_active_feeds(self):
        return [
            {
                "id": 10,
                "url": "https://example.com/feed.xml",
                "title": "Example",
                "description": "Feed",
                "site_url": "https://example.com",
                "etag": None,
                "last_modified": None,
            }
        ]

    async def async_create_feed_item(self, **kwargs):
        self.items.append(kwargs)
        return {"id": 100, **kwargs}

    async def async_list_delivery_targets(self, new_item_ids):
        return [{"id": 100, "subscriber_ids": [1001]}]

    async def async_update_feed_fetch_success(self, **kwargs):
        return None


class _FakeSignalRepo:
    instance = None

    def __init__(self, _db) -> None:
        self.sources: list[dict] = []
        self.items: list[dict] = []
        self.subscriptions: list[dict] = []
        _FakeSignalRepo.instance = self

    async def async_upsert_source(self, **kwargs):
        self.sources.append(kwargs)
        return {"id": 200, **kwargs}

    async def async_upsert_feed_item(self, **kwargs):
        self.items.append(kwargs)
        return {"id": 300, **kwargs}

    async def async_subscribe(self, **kwargs):
        self.subscriptions.append(kwargs)
        return {"id": 400, **kwargs}


@pytest.mark.asyncio
async def test_rss_poll_mirrors_new_items_into_signal_sources(monkeypatch):
    from app.adapters.rss import feed_poller

    monkeypatch.setattr(feed_poller, "SqliteRSSFeedRepositoryAdapter", _FakeRSSRepo)
    monkeypatch.setattr(feed_poller, "SqliteSignalSourceRepositoryAdapter", _FakeSignalRepo)
    monkeypatch.setattr(
        feed_poller,
        "fetch_feed",
        lambda *_args, **_kwargs: FeedResult(
            title="Example",
            description="Feed",
            site_url="https://example.com",
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
        ),
    )

    stats = await feed_poller.poll_all_feeds(SimpleNamespace())

    signal_repo = _FakeSignalRepo.instance
    assert stats["new_item_ids"] == [100]
    assert signal_repo.sources[0]["kind"] == "rss"
    assert signal_repo.items[0]["external_id"] == "guid-1"
    assert signal_repo.subscriptions == [{"user_id": 1001, "source_id": 200}]
