"""Taskiq broker — RedisStreamBroker for durable scheduled-task delivery.

URL resolution order:
  1. TASKIQ_BROKER_REDIS_URL  (explicit override)
  2. REDIS_URL                (shared Redis URL)
  3. redis://{REDIS_HOST}:{REDIS_PORT}/{TASKIQ_BROKER_REDIS_DB}  (component fallback)

Set TASKIQ_BROKER=memory for local dev / tests without Redis.
"""

from __future__ import annotations

import os

from app.tasks.middleware import ChronicFailureMiddleware

_broker_type = os.getenv("TASKIQ_BROKER", "redis").lower()

if _broker_type == "memory":
    from taskiq import InMemoryBroker

    broker = InMemoryBroker()
else:
    from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

    _url = (
        os.getenv("TASKIQ_BROKER_REDIS_URL")
        or os.getenv("REDIS_URL")
        or "redis://{}:{}/{}".format(
            os.getenv("REDIS_HOST", "127.0.0.1"),
            os.getenv("REDIS_PORT", "6379"),
            os.getenv("TASKIQ_BROKER_REDIS_DB", "2"),
        )
    )
    _result_ttl = int(os.getenv("TASKIQ_RESULT_TTL_SEC", "3600"))

    _result_backend: RedisAsyncResultBackend = RedisAsyncResultBackend(
        redis_url=_url,
        result_ex_time=_result_ttl,
    )
    broker = (
        RedisStreamBroker(url=_url)
        .with_result_backend(_result_backend)
        .with_middlewares(ChronicFailureMiddleware())
    )
