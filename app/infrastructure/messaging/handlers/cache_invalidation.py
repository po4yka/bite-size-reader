"""Cache invalidation event handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted
    from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead

logger = logging.getLogger(__name__)


class CacheInvalidationEventHandler:
    """Invalidate caches for entities impacted by domain events."""

    def __init__(self, cache_service: Any | None = None) -> None:
        self._cache = cache_service

    async def on_summary_created(self, event: SummaryCreated) -> None:
        logger.debug(
            "invalidating_summary_cache",
            extra={"summary_id": event.summary_id, "request_id": event.request_id},
        )

        if self._cache:
            try:
                cache_keys = [
                    f"summary:{event.summary_id}",
                    f"request:{event.request_id}",
                    f"request:{event.request_id}:summary",
                    "summaries:unread",
                    "summaries:recent",
                ]

                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={"summary_id": event.summary_id, "keys_invalidated": len(cache_keys)},
                )
            except Exception as exc:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={"summary_id": event.summary_id, "error": str(exc)},
                )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        logger.debug("invalidating_read_status_cache", extra={"summary_id": event.summary_id})

        if self._cache:
            try:
                cache_keys = [
                    f"summary:{event.summary_id}",
                    f"summary:{event.summary_id}:read_status",
                    "summaries:unread",
                ]

                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={"summary_id": event.summary_id, "keys_invalidated": len(cache_keys)},
                )
            except Exception as exc:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={"summary_id": event.summary_id, "error": str(exc)},
                )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        logger.debug("invalidating_request_cache", extra={"request_id": event.request_id})

        if self._cache:
            try:
                cache_keys = [f"request:{event.request_id}", f"request:{event.request_id}:status"]
                for key in cache_keys:
                    await self._cache.delete(key)

                logger.debug(
                    "cache_invalidated",
                    extra={"request_id": event.request_id, "keys_invalidated": len(cache_keys)},
                )
            except Exception as exc:
                logger.warning(
                    "cache_invalidation_failed",
                    extra={"request_id": event.request_id, "error": str(exc)},
                )
