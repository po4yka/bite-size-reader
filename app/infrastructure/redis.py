from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from app.config import AppConfig, RedisConfig

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None
_lock = asyncio.Lock()


def _build_url(cfg: RedisConfig) -> str:
    if cfg.url:
        return cfg.url
    return f"redis://{cfg.host}:{cfg.port}/{cfg.db}"


def redis_key(prefix: str, *parts: str) -> str:
    """Compose a namespaced Redis key."""
    safe_parts = [part for part in parts if part]
    return ":".join([prefix, *safe_parts])


async def get_redis(cfg: AppConfig) -> aioredis.Redis | None:
    """Get or create a shared Redis client.

    Returns None when Redis is disabled or unavailable and not required.
    Raises the connection error when required=True.
    """
    global _client

    if not cfg.redis.enabled:
        return None

    if _client:
        return _client

    async with _lock:
        if _client:
            return _client

        url = _build_url(cfg.redis)
        try:
            _client = aioredis.from_url(
                url,
                password=cfg.redis.password,
                socket_timeout=cfg.redis.socket_timeout,
                decode_responses=True,
            )
            await _client.ping()
            logger.info(
                "redis_connected",
                extra={"url": url, "db": cfg.redis.db, "prefix": cfg.redis.prefix},
            )
            return _client
        except Exception:
            logger.warning(
                "redis_connection_failed",
                exc_info=True,
                extra={"url": url, "db": cfg.redis.db, "required": cfg.redis.required},
            )
            _client = None
            if cfg.redis.required:
                raise
            return None


async def close_redis() -> None:
    """Close shared Redis client if present."""
    global _client
    if _client:
        try:
            await _client.aclose()
            logger.info("redis_closed")
        finally:
            _client = None
