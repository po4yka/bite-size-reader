from __future__ import annotations

import time
from typing import Any

from app.core.json_utils import dumps as json_dumps


class BackgroundProgressPublisher:
    def __init__(self, *, redis: Any | None, logger: Any) -> None:
        self._redis = redis
        self._logger = logger

    async def publish(
        self,
        request_id: int,
        status: str,
        stage: str,
        message: str,
        progress: float,
        error: str | None = None,
    ) -> None:
        if not self._redis:
            return

        payload = {
            "request_id": request_id,
            "status": status,
            "stage": stage,
            "message": message,
            "progress": progress,
            "error": error,
            "timestamp": time.time(),
        }
        channel = f"processing:request:{request_id}"
        try:
            await self._redis.publish(channel, json_dumps(payload))
        except Exception as exc:
            self._logger.warning(
                "bg_redis_publish_failed",
                exc_info=True,
                extra={"channel": channel, "error": str(exc)},
            )
