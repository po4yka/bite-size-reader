"""Retry wrapper for Karakeep sync operations.

This is intentionally separate from the HTTP client retry logic: we retry
high-level sync actions (create/update/tag) based on error semantics.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.adapters.karakeep.sync.constants import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_DELAY_SECONDS,
    DEFAULT_MAX_RETRIES,
)
from app.utils.retry_utils import is_transient_error

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class RetryExecutor:
    async def run(
        self,
        func: Callable[[], Awaitable[Any]],
        *,
        operation_name: str,
        correlation_id: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    ) -> tuple[Any | None, bool, bool, Exception | None]:
        attempt = 0
        delay = base_delay
        last_error: Exception | None = None

        while True:
            try:
                return await func(), True, False, None
            except Exception as exc:
                last_error = exc
                retryable = is_transient_error(exc)
                if not retryable or attempt >= max_retries:
                    if retryable:
                        logger.warning(
                            "karakeep_retry_exhausted",
                            extra={
                                "correlation_id": correlation_id,
                                "operation": operation_name,
                                "attempts": attempt + 1,
                                "error": str(exc),
                            },
                        )
                    return None, False, retryable, last_error

                logger.debug(
                    "karakeep_retrying",
                    extra={
                        "correlation_id": correlation_id,
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "delay_seconds": min(delay, max_delay),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(min(delay, max_delay))
                delay *= DEFAULT_BACKOFF_FACTOR
                attempt += 1
