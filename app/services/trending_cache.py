"""Shared trending topics cache utilities."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.time_utils import UTC
from app.db.models import Request as RequestModel, Summary

TRENDING_CACHE_TTL_SECONDS = 300
TRENDING_MAX_SCAN = 1000


@dataclass(slots=True)
class TrendingCacheEntry:
    expires_at: datetime
    payload: dict[str, Any]


_trending_cache: dict[tuple[int, int, int], TrendingCacheEntry] = {}
_trending_cache_lock = asyncio.Lock()


def _normalize_tag(tag: Any) -> str | None:
    if tag is None:
        return None
    text = str(tag).strip()
    if not text:
        return None
    return text.lower()


def _fetch_trending_records(
    user_id: int,
    *,
    previous_period_start: datetime,
    max_scan: int,
) -> list[tuple[datetime, list[str]]]:
    """Fetch recent summaries with tags for trending computation."""
    records: list[tuple[datetime, list[str]]] = []

    query = (
        Summary.select(Summary.json_payload, RequestModel.created_at)
        .join(RequestModel)
        .where(
            (RequestModel.user_id == user_id) & (RequestModel.created_at >= previous_period_start)
        )
        .order_by(RequestModel.created_at.desc())
        .limit(max_scan)
    )

    for row in query:
        created_at = getattr(row.request, "created_at", None) or getattr(row, "created_at", None)
        payload = row.json_payload or {}
        topic_tags = payload.get("topic_tags") or []
        tag_list = topic_tags if isinstance(topic_tags, list) else []
        if created_at:
            records.append((created_at, tag_list))

    return records


def _build_trending_payload(
    records: list[tuple[datetime, list[str]]],
    *,
    now: datetime,
    days: int,
    limit: int,
) -> dict[str, Any]:
    current_period_start = now - timedelta(days=days)
    previous_period_start = current_period_start - timedelta(days=days)

    current_tags: Counter[str] = Counter()
    previous_tags: Counter[str] = Counter()

    for created_at, raw_tags in records:
        if not created_at:
            continue

        normalized_tags = [_normalize_tag(tag) for tag in raw_tags]
        normalized_tags = [tag for tag in normalized_tags if tag]
        if not normalized_tags:
            continue

        if created_at >= current_period_start:
            current_tags.update(normalized_tags)
        elif created_at >= previous_period_start:
            previous_tags.update(normalized_tags)

    trending_tags = []
    for tag, count in current_tags.most_common(limit):
        prev_count = previous_tags.get(tag, 0)

        if prev_count > 0:
            percentage_change = ((count - prev_count) / prev_count) * 100
        else:
            percentage_change = 100.0 if count > 0 else 0.0

        if percentage_change > 10:
            trend = "up"
        elif percentage_change < -10:
            trend = "down"
        else:
            trend = "stable"

        trending_tags.append(
            {
                "tag": tag,
                "count": count,
                "trend": trend,
                "percentage_change": round(percentage_change, 1),
            }
        )

    return {
        "tags": trending_tags,
        "time_range": {
            "start": current_period_start.isoformat().replace("+00:00", "Z"),
            "end": now.isoformat().replace("+00:00", "Z"),
        },
    }


async def get_trending_payload(user_id: int, *, limit: int, days: int) -> dict[str, Any]:
    """Return trending topics with per-user/param caching."""
    now = datetime.now(UTC)
    cache_key = (user_id, limit, days)

    async with _trending_cache_lock:
        cached = _trending_cache.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.payload

    previous_period_start = now - timedelta(days=days * 2)
    max_scan = min(TRENDING_MAX_SCAN, max(limit * 40, 400))

    records = await asyncio.to_thread(
        _fetch_trending_records,
        user_id,
        previous_period_start=previous_period_start,
        max_scan=max_scan,
    )

    payload = _build_trending_payload(records, now=now, days=days, limit=limit)

    async with _trending_cache_lock:
        _trending_cache[cache_key] = TrendingCacheEntry(
            expires_at=now + timedelta(seconds=TRENDING_CACHE_TTL_SECONDS),
            payload=payload,
        )

    return payload


def clear_trending_cache() -> None:
    """Clear cached trending results (e.g., after summary writes)."""
    _trending_cache.clear()
