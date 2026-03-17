from datetime import datetime, timedelta

import pytest

from app.core.time_utils import UTC
from app.infrastructure.cache import trending_cache


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


@pytest.mark.asyncio
async def test_trending_payload_prunes_expired_in_memory_entries(monkeypatch):
    trending_cache.clear_trending_cache()

    expired_key = (999, 1, 1)
    trending_cache._trending_cache[expired_key] = trending_cache.TrendingCacheEntry(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        payload={"tags": []},
    )

    async def fake_get_from_redis(user_id: int, days: int, limit: int):
        del user_id, days, limit

    async def fake_set_to_redis(
        user_id: int, days: int, limit: int, payload: dict[str, object]
    ) -> bool:
        del user_id, days, limit, payload
        return False

    def fake_fetch(user_id: int, *, previous_period_start: datetime, max_scan: int):
        del user_id, previous_period_start, max_scan
        return []

    monkeypatch.setattr(trending_cache, "_get_from_redis", fake_get_from_redis)
    monkeypatch.setattr(trending_cache, "_set_to_redis", fake_set_to_redis)
    monkeypatch.setattr(trending_cache, "_fetch_trending_records", fake_fetch)

    await trending_cache.get_trending_payload(1, limit=5, days=30)

    assert expired_key not in trending_cache._trending_cache

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
