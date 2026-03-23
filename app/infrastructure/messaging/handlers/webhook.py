"""Webhook event handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.domain.services.webhook_service import is_webhook_url_safe

if TYPE_CHECKING:
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryCreated

logger = get_logger(__name__)


class WebhookEventHandler:
    """Send HTTP webhooks for domain events when configured."""

    def __init__(self, webhook_client: Any | None = None, webhook_url: str | None = None) -> None:
        self._webhook_client = webhook_client
        self._webhook_url = webhook_url

    def _check_url_safe(self, event_type: str) -> bool:
        """Return True if the configured webhook URL passes SSRF checks."""
        if not self._webhook_url:
            return False
        safe, err = is_webhook_url_safe(self._webhook_url)
        if not safe:
            logger.warning(
                "webhook_blocked_ssrf",
                extra={"event_type": event_type, "reason": err},
            )
        return safe

    async def on_summary_created(self, event: SummaryCreated) -> None:
        logger.debug(
            "sending_summary_created_webhook",
            extra={"summary_id": event.summary_id, "request_id": event.request_id},
        )

        if self._webhook_client and self._webhook_url and self._check_url_safe("summary.created"):
            try:
                payload = {
                    "event_type": "summary.created",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {
                        "summary_id": event.summary_id,
                        "request_id": event.request_id,
                        "language": event.language,
                        "has_insights": event.has_insights,
                    },
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "summary.created",
                        "summary_id": event.summary_id,
                        "webhook_url": self._webhook_url,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "summary.created",
                        "summary_id": event.summary_id,
                        "error": str(exc),
                    },
                )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        logger.debug(
            "sending_request_completed_webhook",
            extra={"request_id": event.request_id, "summary_id": event.summary_id},
        )

        if self._webhook_client and self._webhook_url and self._check_url_safe("request.completed"):
            try:
                payload = {
                    "event_type": "request.completed",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {"request_id": event.request_id, "summary_id": event.summary_id},
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "request.completed",
                        "request_id": event.request_id,
                        "webhook_url": self._webhook_url,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "request.completed",
                        "request_id": event.request_id,
                        "error": str(exc),
                    },
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        logger.debug(
            "sending_request_failed_webhook",
            extra={"request_id": event.request_id, "error_message": event.error_message},
        )

        if self._webhook_client and self._webhook_url and self._check_url_safe("request.failed"):
            try:
                payload = {
                    "event_type": "request.failed",
                    "event_id": f"{event.aggregate_id}_{event.occurred_at.isoformat()}",
                    "timestamp": event.occurred_at.isoformat(),
                    "data": {
                        "request_id": event.request_id,
                        "error_message": event.error_message,
                        "error_details": event.error_details,
                    },
                }

                await self._webhook_client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "webhook_sent",
                    extra={
                        "event_type": "request.failed",
                        "request_id": event.request_id,
                        "webhook_url": self._webhook_url,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "webhook_send_failed",
                    extra={
                        "event_type": "request.failed",
                        "request_id": event.request_id,
                        "error": str(exc),
                    },
                )
