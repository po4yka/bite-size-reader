from __future__ import annotations

import datetime as dt

import httpx
import pytest

from app.adapters.ingestors.hn import HackerNewsIngester
from app.application.ports.source_ingestors import RateLimitedSourceError


class _FakeClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.urls.append(url)
        payload = self.responses[url]
        if isinstance(payload, int):
            return httpx.Response(payload, request=httpx.Request("GET", url))
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_hn_ingester_normalizes_items_with_engagement() -> None:
    client = _FakeClient(
        {
            "https://hacker-news.firebaseio.com/v0/topstories.json": [42],
            "https://hacker-news.firebaseio.com/v0/item/42.json": {
                "id": 42,
                "type": "story",
                "title": "Launch",
                "url": "https://example.com/launch?utm_source=hn",
                "by": "pg",
                "score": 123,
                "descendants": 45,
                "time": 1_777_500_000,
            },
        }
    )
    ingester = HackerNewsIngester(feed="top", limit=1, client=client)

    result = await ingester.fetch()

    assert result.source.kind == "hacker_news"
    assert result.source.external_id == "hn:top"
    assert result.items[0].external_id == "hn:42"
    assert result.items[0].canonical_url == "https://example.com/launch"
    assert result.items[0].author == "pg"
    assert result.items[0].published_at == dt.datetime.fromtimestamp(1_777_500_000, tz=dt.UTC)
    assert result.items[0].engagement == {"score": 123.0, "comments": 45}


@pytest.mark.asyncio
async def test_hn_ingester_turns_429_into_rate_limit_error() -> None:
    client = _FakeClient({"https://hacker-news.firebaseio.com/v0/newstories.json": 429})
    ingester = HackerNewsIngester(feed="new", client=client)

    with pytest.raises(RateLimitedSourceError):
        await ingester.fetch()
