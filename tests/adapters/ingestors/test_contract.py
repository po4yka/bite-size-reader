from __future__ import annotations

import datetime as dt

import pytest

from app.adapters.ingestors.runner import SourceIngestionRunner
from app.application.ports.source_ingestors import (
    IngestedFeedItem,
    IngestedSource,
    SourceFetchResult,
    SourceIngester,
)
from app.core.time_utils import UTC


class _FakeRepository:
    def __init__(self) -> None:
        self.sources: list[dict] = []
        self.items: list[dict] = []
        self.subscriptions: list[dict] = []
        self.successes: list[int] = []
        self.errors: list[dict] = []

    async def async_upsert_source(self, **kwargs):
        self.sources.append(kwargs)
        return {"id": len(self.sources), **kwargs}

    async def async_upsert_feed_item(self, **kwargs):
        self.items.append(kwargs)
        return {"id": len(self.items), **kwargs}

    async def async_subscribe(self, **kwargs):
        self.subscriptions.append(kwargs)
        return {"id": len(self.subscriptions), **kwargs}

    async def async_record_source_fetch_success(self, source_id: int):
        self.successes.append(source_id)

    async def async_record_source_fetch_error(self, **kwargs):
        self.errors.append(kwargs)
        return False


class _FakeIngester:
    name = "fake"

    def is_enabled(self) -> bool:
        return True

    async def fetch(self) -> SourceFetchResult:
        return SourceFetchResult(
            source=IngestedSource(
                kind="fake",
                external_id="fake:one",
                url="https://example.test/feed",
                title="Fake",
                metadata={"source": "test"},
            ),
            items=[
                IngestedFeedItem(
                    external_id="item-1",
                    canonical_url="https://example.test/item",
                    title="Item",
                    content_text="Body",
                    author="Author",
                    published_at=dt.datetime(2026, 4, 30, tzinfo=UTC),
                    engagement={"comments": 3, "score": 4.0},
                    metadata={"raw": True},
                )
            ],
        )


def test_source_ingester_protocol_is_runtime_checkable() -> None:
    assert isinstance(_FakeIngester(), SourceIngester)


@pytest.mark.asyncio
async def test_runner_persists_normalized_items_and_subscriptions() -> None:
    repo = _FakeRepository()
    runner = SourceIngestionRunner(
        repository=repo,
        ingesters=[_FakeIngester()],
        subscriber_user_ids=[1001],
    )

    stats = await runner.run_once()

    assert stats == {"enabled": 1, "sources": 1, "items": 1, "errors": 0, "skipped": 0}
    assert repo.sources[0]["kind"] == "fake"
    assert repo.items[0]["external_id"] == "item-1"
    assert repo.items[0]["engagement"]["comments"] == 3
    assert repo.subscriptions == [{"user_id": 1001, "source_id": 1}]
    assert repo.successes == [1]
