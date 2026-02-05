"""Analytics event handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryMarkedAsRead

logger = logging.getLogger(__name__)


class AnalyticsEventHandler:
    """Track domain events via an optional analytics client."""

    def __init__(self, analytics_service: Any | None = None) -> None:
        self._analytics = analytics_service

    async def on_request_completed(self, event: RequestCompleted) -> None:
        logger.info(
            "request_completed_analytics",
            extra={
                "request_id": event.request_id,
                "summary_id": event.summary_id,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

        if self._analytics:
            try:
                await self._analytics.track(
                    "request_completed",
                    {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_completed", "error": str(exc)},
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        logger.warning(
            "request_failed_analytics",
            extra={
                "request_id": event.request_id,
                "error_message": event.error_message,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

        if self._analytics:
            try:
                await self._analytics.track(
                    "request_failed",
                    {
                        "request_id": event.request_id,
                        "error_message": event.error_message,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_failed", "error": str(exc)},
                )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        logger.debug("summary_read_analytics", extra={"summary_id": event.summary_id})

        if self._analytics:
            try:
                await self._analytics.track(
                    "summary_marked_as_read",
                    {"summary_id": event.summary_id, "timestamp": event.occurred_at.isoformat()},
                )
            except Exception as exc:
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "summary_marked_as_read", "error": str(exc)},
                )
