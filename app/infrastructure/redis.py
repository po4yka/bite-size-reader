from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from app.config import AppConfig, RedisConfig

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None
_lock = asyncio.Lock()

# Connection state tracking for reconnection logic
_last_connection_attempt: float = 0.0
_last_error: str | None = None
_connection_failed: bool = False


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

    Implements reconnection logic with rate-limiting:
    - If connection failed previously, waits for reconnect_interval before retrying
    - Logs at INFO level (not WARNING) when Redis is optional and unavailable
    - Only logs full traceback when REDIS_REQUIRED=true
    """
    global _client, _last_connection_attempt, _last_error, _connection_failed

    if not cfg.redis.enabled:
        return None

    async with _lock:
        # Return existing healthy connection
        if _client is not None:
            return _client

        # Rate-limit reconnection attempts
        now = time.time()
        reconnect_interval = cfg.redis.reconnect_interval
        if _connection_failed and reconnect_interval > 0:
            elapsed = now - _last_connection_attempt
            if elapsed < reconnect_interval:
                # Too soon to retry, return None silently
                return None

        _last_connection_attempt = now
        url = _build_url(cfg.redis)

        try:
            _client = aioredis.from_url(
                url,
                password=cfg.redis.password,
                socket_timeout=cfg.redis.socket_timeout,
                decode_responses=True,
            )
            ping_result = _client.ping()
            if inspect.isawaitable(ping_result):
                await ping_result

            # Log reconnection if we had failed before
            if _connection_failed:
                logger.info(
                    "redis_reconnected",
                    extra={"url": url, "db": cfg.redis.db, "prefix": cfg.redis.prefix},
                )
            else:
                logger.info(
                    "redis_connected",
                    extra={"url": url, "db": cfg.redis.db, "prefix": cfg.redis.prefix},
                )

            # Reset failure state
            _connection_failed = False
            _last_error = None
            return _client

        except Exception as exc:
            _client = None
            _connection_failed = True
            _last_error = str(exc)

            if cfg.redis.required:
                # Required: log error with full traceback
                logger.error(
                    "redis_connection_failed",
                    exc_info=True,
                    extra={"url": url, "db": cfg.redis.db, "required": True},
                )
                raise

            # Optional: log as INFO without traceback (single line)
            logger.info(
                "redis_unavailable",
                extra={"url": url, "error": _last_error},
            )
            return None


def get_connection_state() -> dict[str, bool | float | str | None]:
    """Get current Redis connection state for health checks.

    Returns:
        Dict with keys:
        - connected: bool - whether client is connected
        - last_attempt: float - unix timestamp of last connection attempt (0 if never)
        - last_error: str | None - last error message if connection failed
        - connection_failed: bool - whether last connection attempt failed
    """
    return {
        "connected": _client is not None,
        "last_attempt": _last_connection_attempt,
        "last_error": _last_error,
        "connection_failed": _connection_failed,
    }


async def close_redis() -> None:
    """Close shared Redis client if present."""
    global _client, _connection_failed, _last_error
    if _client:
        try:
            await _client.aclose()
            logger.info("redis_closed")
        finally:
            _client = None
            _connection_failed = False
            _last_error = None
