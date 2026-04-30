from __future__ import annotations

import pytest

from app.adapters.ingestors.twitter import TwitterIngester, TwitterIngestionConfig


def test_twitter_ingester_is_disabled_by_default() -> None:
    ingester = TwitterIngester(TwitterIngestionConfig())

    assert ingester.is_enabled() is False


@pytest.mark.asyncio
async def test_twitter_ingester_requires_cost_acknowledgement(caplog) -> None:
    ingester = TwitterIngester(TwitterIngestionConfig(enabled=True, ack_cost=False))

    assert ingester.is_enabled() is False
    assert "twitter_ingestion_disabled_cost_ack_missing" in caplog.text
    with pytest.raises(RuntimeError, match="cost acknowledgement"):
        await ingester.fetch()
