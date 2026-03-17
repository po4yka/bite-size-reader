"""Push notification event handler for summary-ready events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.summary_events import SummaryCreated
    from app.infrastructure.push.service import PushNotificationService

logger = logging.getLogger(__name__)


class PushNotificationEventHandler:
    """Send mobile push notifications when a summary becomes ready."""

    def __init__(
        self,
        push_service: PushNotificationService,
        summary_repository: Any,
        request_repository: Any,
    ) -> None:
        self._push = push_service
        self._summary_repo = summary_repository
        self._request_repo = request_repository

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Handle SummaryCreated -- push 'Your summary is ready' to the owner."""
        try:
            # Resolve the owning user from the request
            request_data = await self._request_repo.async_get_request(event.request_id)
            if not request_data:
                logger.debug(
                    "push_skip_no_request",
                    extra={"request_id": event.request_id},
                )
                return

            user_id = request_data.get("user_id")
            if not user_id:
                logger.debug(
                    "push_skip_no_user",
                    extra={"request_id": event.request_id},
                )
                return

            # Build notification body from the summary payload
            body = self._build_body(event, request_data)

            data: dict[str, str] = {
                "summary_id": str(event.summary_id),
                "type": "summary_ready",
            }

            await self._push.send_to_user(
                user_id=int(user_id),
                title="Your summary is ready",
                body=body,
                data=data,
            )

        except Exception as exc:
            # Never let a push failure bubble up and break the event bus pipeline
            logger.warning(
                "push_notification_handler_error",
                extra={
                    "request_id": event.request_id,
                    "summary_id": event.summary_id,
                    "error": str(exc),
                },
            )

    # ------------------------------------------------------------------

    def _build_body(self, event: SummaryCreated, request_data: dict[str, Any]) -> str:
        """Derive the notification body text.

        Tries, in order:
        1. The summary ``tldr`` field (truncated to 100 chars)
        2. The domain of the source URL
        3. A generic fallback
        """
        # Try to get tldr from summary
        try:
            summary_data = self._get_summary_sync(event.summary_id)
            if summary_data:
                payload = summary_data.get("json_payload") or {}
                if isinstance(payload, dict):
                    tldr = payload.get("tldr")
                    if tldr and isinstance(tldr, str):
                        return tldr[:100] + ("..." if len(tldr) > 100 else "")
        except Exception:
            pass

        # Fall back to URL domain
        url = request_data.get("input_url") or request_data.get("normalized_url")
        if url and isinstance(url, str):
            try:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                if domain:
                    return domain
            except Exception:
                pass

        return "Tap to read your new summary"

    def _get_summary_sync(self, summary_id: int) -> dict[str, Any] | None:
        """Synchronously fetch summary data (called within an async handler).

        Uses the Peewee ORM directly since we are already inside the event bus
        handler and the underlying DB call is non-blocking on SQLite.
        """
        try:
            from app.db.models import Summary, model_to_dict

            summary = Summary.get_or_none(Summary.id == summary_id)
            return model_to_dict(summary)
        except Exception:
            return None
