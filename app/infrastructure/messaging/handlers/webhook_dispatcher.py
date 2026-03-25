"""Per-user webhook dispatcher.

Fans out domain events to individual user webhook subscriptions,
with HMAC signing, delivery logging, and automatic disabling
after repeated failures.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import httpx

from app.core.logging_utils import get_logger
from app.domain.services.webhook_service import (
    build_webhook_payload,
    is_webhook_url_safe,
    sign_payload,
)

if TYPE_CHECKING:
    from app.application.ports.requests import RequestRepositoryPort
    from app.application.ports.rules import WebhookRepositoryPort
    from app.domain.events.request_events import RequestCompleted, RequestFailed
    from app.domain.events.summary_events import SummaryCreated
    from app.domain.events.tag_events import TagAttached, TagDetached

logger = get_logger(__name__)

_MAX_FAILURES = 10
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 30.0


class WebhookDispatcher:
    """Dispatches domain events to per-user webhook subscriptions."""

    def __init__(
        self,
        webhook_repository: WebhookRepositoryPort,
        request_repository: RequestRepositoryPort,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._repo = webhook_repository
        self._request_repository = request_repository
        self._http_client = http_client
        self._owns_client = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=_CONNECT_TIMEOUT,
                    read=_READ_TIMEOUT,
                    write=_READ_TIMEOUT,
                    pool=_READ_TIMEOUT,
                ),
            )
            self._owns_client = True
        return self._http_client

    async def dispatch(self, event_type: str, user_id: int, data: dict[str, Any]) -> None:
        """Fan out event to all matching user webhook subscriptions."""
        subscriptions = await self._repo.async_get_user_subscriptions(user_id, enabled_only=True)

        if not subscriptions:
            logger.debug(
                "webhook_dispatch_no_subscriptions",
                extra={"event_type": event_type, "user_id": user_id},
            )
            return

        client = await self._get_client()

        for sub in subscriptions:
            sub_id: int = sub["id"]
            events_list: list[str] = sub.get("events_json") or []

            # Filter: subscription must listen for this event type (or "*" for all)
            if "*" not in events_list and event_type not in events_list:
                continue

            try:
                await self._deliver(client, sub, event_type, data)
            except Exception:
                logger.exception(
                    "webhook_dispatch_unexpected_error",
                    extra={"subscription_id": sub_id, "event_type": event_type},
                )

    async def _deliver(
        self,
        client: httpx.AsyncClient,
        sub: dict[str, Any],
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Deliver a single webhook, log result, and manage failure count."""
        sub_id: int = sub["id"]
        url: str = sub["url"]
        secret: str = sub["secret"]

        # Pre-delivery SSRF check (guards against DNS rebinding)
        url_safe, ssrf_error = is_webhook_url_safe(url)
        if not url_safe:
            logger.warning(
                "webhook_delivery_blocked_ssrf",
                extra={
                    "subscription_id": sub_id,
                    "event_type": event_type,
                    "reason": ssrf_error,
                },
            )
            return

        payload = build_webhook_payload(event_type, data)
        payload_bytes = json.dumps(payload, default=str).encode()
        signature = sign_payload(secret, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-BSR-Signature": f"sha256={signature}",
            "X-BSR-Event": event_type,
        }

        start = time.monotonic()
        response_status: int | None = None
        response_body: str | None = None
        error_msg: str | None = None
        success = False

        try:
            response = await client.post(url, content=payload_bytes, headers=headers)
            response_status = response.status_code
            response_body = response.text[:2048]  # cap stored body
            success = 200 <= response.status_code < 300
        except httpx.TimeoutException as exc:
            error_msg = f"Timeout: {exc}"
        except httpx.HTTPError as exc:
            error_msg = f"HTTP error: {exc}"
        except Exception as exc:
            error_msg = f"Unexpected: {exc}"

        duration_ms = int((time.monotonic() - start) * 1000)

        # Log delivery attempt
        await self._repo.async_log_delivery(
            subscription_id=sub_id,
            event_type=event_type,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            duration_ms=duration_ms,
            success=success,
            attempt=1,
            error=error_msg,
        )

        if success:
            await self._repo.async_reset_failure_count(sub_id)
            logger.info(
                "webhook_delivered",
                extra={
                    "subscription_id": sub_id,
                    "event_type": event_type,
                    "status": response_status,
                    "duration_ms": duration_ms,
                },
            )
        else:
            new_count = await self._repo.async_increment_failure_count(sub_id)
            logger.warning(
                "webhook_delivery_failed",
                extra={
                    "subscription_id": sub_id,
                    "event_type": event_type,
                    "error": error_msg,
                    "status": response_status,
                    "failure_count": new_count,
                    "duration_ms": duration_ms,
                },
            )
            if new_count >= _MAX_FAILURES:
                await self._repo.async_disable_subscription(sub_id)
                logger.warning(
                    "webhook_subscription_disabled",
                    extra={
                        "subscription_id": sub_id,
                        "reason": f"consecutive failures reached {_MAX_FAILURES}",
                    },
                )

    # ------------------------------------------------------------------
    # Event handler methods
    # ------------------------------------------------------------------

    async def _user_id_from_request(self, request_id: int) -> int | None:
        """Look up user_id from the request repository."""
        request = await self._request_repository.async_get_request_by_id(request_id)
        if request is None:
            logger.warning(
                "webhook_dispatcher_request_not_found",
                extra={"request_id": request_id},
            )
            return None
        user_id = request.get("user_id")
        return int(user_id) if user_id is not None else None

    async def on_summary_created(self, event: SummaryCreated) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self.dispatch(
            "summary.created",
            user_id,
            {
                "summary_id": event.summary_id,
                "request_id": event.request_id,
                "language": event.language,
                "has_insights": event.has_insights,
            },
        )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self.dispatch(
            "request.completed",
            user_id,
            {
                "request_id": event.request_id,
                "summary_id": event.summary_id,
            },
        )

    async def on_request_failed(self, event: RequestFailed) -> None:
        user_id = await self._user_id_from_request(event.request_id)
        if user_id is None:
            return
        await self.dispatch(
            "request.failed",
            user_id,
            {
                "request_id": event.request_id,
                "error_message": event.error_message,
                "error_details": event.error_details,
            },
        )

    async def on_tag_attached(self, event: TagAttached) -> None:
        await self.dispatch(
            "tag.attached",
            event.user_id,
            {
                "summary_id": event.summary_id,
                "tag_id": event.tag_id,
                "source": event.source,
            },
        )

    async def on_tag_detached(self, event: TagDetached) -> None:
        await self.dispatch(
            "tag.detached",
            event.user_id,
            {
                "summary_id": event.summary_id,
                "tag_id": event.tag_id,
            },
        )
