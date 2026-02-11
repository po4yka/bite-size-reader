"""Shared trending topics cache utilities.

Supports both Redis (shared across workers) and in-memory (fallback) caching.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.time_utils import UTC
from app.db.models import Request as RequestModel, Summary

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.infrastructure.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)

TRENDING_CACHE_TTL_SECONDS = 300
TRENDING_MAX_SCAN = 1000


@dataclass(slots=True)
class TrendingCacheEntry:
    expires_at: datetime
    payload: dict[str, Any]


# In-memory fallback cache
_trending_cache: dict[tuple[int, int, int], TrendingCacheEntry] = {}
_trending_cache_lock = asyncio.Lock()

# Redis cache singleton (lazily initialized)
_redis_cache: RedisCache | None = None
_app_config: AppConfig | None = None


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


def _get_redis_cache() -> tuple[RedisCache | None, AppConfig | None]:
    """Get or initialize the Redis cache singleton."""
    global _redis_cache, _app_config

    if _redis_cache is not None:
        return _redis_cache, _app_config

    try:
        from app.config import load_config
        from app.infrastructure.cache.redis_cache import RedisCache

        _app_config = load_config(allow_stub_telegram=True)
        if not _app_config.redis.enabled:
            return None, _app_config

        _redis_cache = RedisCache(_app_config)
        return _redis_cache, _app_config
    except Exception as exc:
        logger.debug(
            "trending_redis_cache_init_skipped",
            extra={"error": str(exc)},
        )
        return None, None


async def _get_from_redis(user_id: int, days: int, limit: int) -> dict[str, Any] | None:
    """Try to get trending payload from Redis cache."""
    redis_cache, cfg = _get_redis_cache()
    if redis_cache is None or cfg is None:
        return None

    try:
        cached = await redis_cache.get_json("trending", str(user_id), str(days), str(limit))
        if isinstance(cached, dict):
            logger.debug(
                "trending_redis_cache_hit",
                extra={"user_id": user_id, "days": days, "limit": limit},
            )
            return cached
    except Exception as exc:
        logger.warning(
            "trending_redis_cache_get_failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
    return None


async def _set_to_redis(user_id: int, days: int, limit: int, payload: dict[str, Any]) -> bool:
    """Store trending payload in Redis cache."""
    redis_cache, cfg = _get_redis_cache()
    if redis_cache is None or cfg is None:
        return False

    try:
        ttl = cfg.redis.trending_cache_ttl_seconds
        success = await redis_cache.set_json(
            value=payload,
            ttl_seconds=ttl,
            parts=("trending", str(user_id), str(days), str(limit)),
        )
        if success:
            logger.debug(
                "trending_redis_cached",
                extra={"user_id": user_id, "days": days, "limit": limit, "ttl": ttl},
            )
        return success
    except Exception as exc:
        logger.warning(
            "trending_redis_cache_set_failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
        return False


async def get_trending_payload(user_id: int, *, limit: int, days: int) -> dict[str, Any]:
    """Return trending topics with per-user/param caching.

    Uses Redis cache if available, falls back to in-memory cache otherwise.
    """
    now = datetime.now(UTC)

    # Try Redis cache first
    redis_cached = await _get_from_redis(user_id, days, limit)
    if redis_cached is not None:
        return redis_cached

    # Fall back to in-memory cache
    cache_key = (user_id, limit, days)
    async with _trending_cache_lock:
        cached = _trending_cache.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.payload

    # Cache miss - compute trending
    previous_period_start = now - timedelta(days=days * 2)
    max_scan = min(TRENDING_MAX_SCAN, max(limit * 40, 400))

    records = await asyncio.to_thread(
        _fetch_trending_records,
        user_id,
        previous_period_start=previous_period_start,
        max_scan=max_scan,
    )

    payload = _build_trending_payload(records, now=now, days=days, limit=limit)

    # Cache in Redis (non-blocking, failures are logged but ignored)
    await _set_to_redis(user_id, days, limit, payload)

    # Also cache in memory as immediate fallback
    async with _trending_cache_lock:
        _trending_cache[cache_key] = TrendingCacheEntry(
            expires_at=now + timedelta(seconds=TRENDING_CACHE_TTL_SECONDS),
            payload=payload,
        )

    return payload


def clear_trending_cache() -> None:
    """Clear cached trending results (e.g., after summary writes).

    Clears both in-memory and Redis caches.
    """
    _trending_cache.clear()

    # Clear Redis cache asynchronously if available
    redis_cache, cfg = _get_redis_cache()
    if redis_cache is not None and cfg is not None:
        try:
            # Schedule async clear without blocking
            asyncio.get_event_loop().create_task(_clear_redis_trending_cache())
        except RuntimeError:
            # No event loop running, skip Redis clear
            pass


async def _clear_redis_trending_cache() -> None:
    """Clear all trending entries from Redis cache."""
    redis_cache, cfg = _get_redis_cache()
    if redis_cache is None or cfg is None:
        return

    try:
        deleted = await redis_cache.clear()
        logger.debug(
            "trending_redis_cache_cleared",
            extra={"deleted_count": deleted},
        )
    except Exception as exc:
        logger.warning(
            "trending_redis_cache_clear_failed",
            extra={"error": str(exc)},
        )
