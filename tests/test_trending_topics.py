from datetime import datetime, timedelta

import pytest

from app.core.time_utils import UTC
from app.services import trending_cache


@pytest.mark.asyncio
async def test_trending_payload_is_cached(monkeypatch):
    trending_cache.clear_trending_cache()

    call_count = {"value": 0}

    def fake_fetch(user_id: int, *, previous_period_start: datetime, max_scan: int):
        call_count["value"] += 1
        now = datetime.now(UTC)
        return [(now - timedelta(days=1), ["AI", "#AI", "ml"])]

    monkeypatch.setattr(trending_cache, "_fetch_trending_records", fake_fetch)
    monkeypatch.setattr(trending_cache, "TRENDING_CACHE_TTL_SECONDS", 60)

    first = await trending_cache.get_trending_payload(1, limit=5, days=30)
    second = await trending_cache.get_trending_payload(1, limit=5, days=30)

    assert call_count["value"] == 1
    assert first == second

    trending_cache.clear_trending_cache()


def test_build_trending_payload_uses_previous_period():
    now = datetime(2025, 1, 10, tzinfo=UTC)
    records = [
        (now - timedelta(days=2), ["ai", "AI"]),
        (now - timedelta(days=15), ["ai"]),
    ]

    payload = trending_cache._build_trending_payload(records, now=now, days=10, limit=5)

    assert payload["tags"][0]["tag"] == "ai"
    assert payload["tags"][0]["count"] == 2
    assert payload["tags"][0]["trend"] == "up"
