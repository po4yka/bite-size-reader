from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .models import RetryPolicy


class BackgroundRetryRunner:
    def __init__(self, *, policy: RetryPolicy, logger: Any) -> None:
        self._policy = policy
        self._logger = logger

    async def run_with_backoff(
        self,
        func: Callable[[], Awaitable[Any]],
        stage: str,
        correlation_id: str,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._policy.attempts + 1):
            try:
                return await func()
            except Exception as exc:
                raise_if_cancelled(exc)
                last_error = exc
                delay_ms = min(
                    self._policy.max_delay_ms,
                    int(self._policy.base_delay_ms * (2 ** (attempt - 1))),
                )
                jitter = int(delay_ms * self._policy.jitter_ratio)
                delay_ms = max(0, delay_ms + random.randint(-jitter, jitter))

                if attempt >= self._policy.attempts:
                    break

                self._logger.warning(
                    "bg_retry",
                    extra={
                        "correlation_id": correlation_id,
                        "stage": stage,
                        "attempt": attempt,
                        "delay_ms": delay_ms,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay_ms / 1000)

        if last_error:
            raise last_error
        raise RuntimeError("Retry loop exited without result or error")
