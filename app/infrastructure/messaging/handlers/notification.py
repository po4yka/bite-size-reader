"""User notification event handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted, RequestFailed

logger = logging.getLogger(__name__)


class NotificationEventHandler:
    """Send user-facing notifications when domain events occur."""

    def __init__(
        self,
        telegram_client: Any | None = None,
        notification_service: Any | None = None,
    ) -> None:
        self._telegram = telegram_client
        self._notification_service = notification_service

    async def on_request_completed(self, event: RequestCompleted) -> None:
        logger.debug(
            "request_completed_notification",
            extra={"request_id": event.request_id, "summary_id": event.summary_id},
        )

        if self._telegram:
            try:
                logger.debug(
                    "notification_would_be_sent",
                    extra={"request_id": event.request_id, "channel": "telegram"},
                )
            except Exception as exc:
                logger.warning(
                    "notification_send_failed",
                    extra={
                        "request_id": event.request_id,
                        "channel": "telegram",
                        "error": str(exc),
                    },
                )

        if self._notification_service:
            try:
                await self._notification_service.send(
                    "request_completed",
                    {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "notification_send_failed",
                    extra={
                        "request_id": event.request_id,
                        "channel": "notification_service",
                        "error": str(exc),
                    },
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        logger.debug(
            "request_failed_notification",
            extra={"request_id": event.request_id, "error_message": event.error_message},
        )

        if self._telegram:
            try:
                logger.debug(
                    "failure_notification_would_be_sent",
                    extra={"request_id": event.request_id, "channel": "telegram"},
                )
            except Exception as exc:
                logger.warning(
                    "notification_send_failed",
                    extra={"request_id": event.request_id, "error": str(exc)},
                )
