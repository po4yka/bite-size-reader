import json
from enum import Enum

import fakeredis.aioredis
import pytest
from starlette.requests import Request
from starlette.responses import Response


# Python 3.10 compatibility shim (must be before app imports)
class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""


import enum

enum.StrEnum = StrEnum  # type: ignore[misc,assignment]

from app.api import middleware
from app.api.services.sync_service import SyncService
from app.config import ApiLimitsConfig, RedisConfig, SyncConfig
from app.infrastructure.redis import redis_key


class DummyCfg:
    def __init__(self, *, required: bool = False, limit: int = 5, window_seconds: int = 60):
        self.redis = RedisConfig(enabled=True, required=required, prefix="test")
        self.api_limits = ApiLimitsConfig(
            window_seconds=window_seconds,
            cooldown_multiplier=1.0,
            max_concurrent=3,
            default_limit=limit,
            summaries_limit=limit,
            requests_limit=limit,
            search_limit=limit,
        )
        self.sync = SyncConfig(expiry_hours=1, default_limit=100, min_limit=1, max_limit=500)


@pytest.mark.asyncio
async def test_rate_limit_allows_then_blocks(monkeypatch):
    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cfg = DummyCfg(limit=1, window_seconds=1)

    middleware._cfg = cfg
    middleware._redis_warning_logged = False

    async def fake_get_redis(_: DummyCfg):
        return redis_client

    monkeypatch.setattr(middleware, "get_redis", fake_get_redis)

    async def call_next(_: Request):
        return Response(status_code=200)

    request1 = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/requests",
            "headers": [],
            "client": ("127.0.0.1", 0),
        }
    )
    first = await middleware.rate_limit_middleware(request1, call_next)
    assert getattr(first, "status_code", None) == 200
    headers1 = getattr(first, "headers", {})
    assert headers1.get("X-RateLimit-Limit") == "1"
    assert headers1.get("X-RateLimit-Remaining") == "0"

    request2 = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/requests",
            "headers": [],
            "client": ("127.0.0.1", 0),
        }
    )
    second = await middleware.rate_limit_middleware(request2, call_next)
    assert getattr(second, "status_code", None) == 429
    headers2 = getattr(second, "headers", None)
    if headers2 is not None:
        assert headers2.get("Retry-After") in {"1", "0"}
    payload = getattr(second, "body", b"") or getattr(second, "content", b"")
    if isinstance(payload, bytes | bytearray):
        data = json.loads(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {}
    assert data.get("error", {}).get("retry_after") is not None

    await redis_client.flushall()


@pytest.mark.asyncio
async def test_rate_limit_backend_required_returns_503(monkeypatch):
    cfg = DummyCfg(required=True, limit=1, window_seconds=1)
    middleware._cfg = cfg
    middleware._redis_warning_logged = False

    async def fake_get_redis(_: DummyCfg):
        return None

    monkeypatch.setattr(middleware, "get_redis", fake_get_redis)

    async def call_next(_: Request):
        return Response(status_code=200)

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/requests",
            "headers": [],
            "client": ("127.0.0.1", 0),
        }
    )
    resp = await middleware.rate_limit_middleware(request, call_next)

    assert getattr(resp, "status_code", None) == 503
    body = getattr(resp, "body", b"") or getattr(resp, "content", b"")
    if isinstance(body, bytes | bytearray):
        data = json.loads(body)
    elif isinstance(body, dict):
        data = body
    else:
        data = {}
    assert data.get("error", {}).get("code") == "RATE_LIMIT_BACKEND_UNAVAILABLE"


@pytest.mark.asyncio
async def test_sync_session_stored_in_redis(monkeypatch):
    from unittest.mock import MagicMock

    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cfg = DummyCfg(limit=1, window_seconds=1)

    # Create a mock session manager since SyncService now requires it
    mock_session_manager = MagicMock()
    svc = SyncService(cfg, mock_session_manager)

    async def fake_get_redis(_: DummyCfg):
        return redis_client

    monkeypatch.setattr("app.api.services.sync_service.get_redis", fake_get_redis)

    session = await svc.start_session(user_id=1, client_id="client", limit=50)

    key = redis_key(cfg.redis.prefix, "sync", "session", session.session_id)
    ttl = await redis_client.ttl(key)
    assert ttl > 0
    stored = await redis_client.get(key)
    assert stored is not None

    await redis_client.flushall()
