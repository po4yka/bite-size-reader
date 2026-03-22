"""SQLite implementation of webhook repository.

This adapter handles persistence for webhook subscriptions and delivery logs.
"""

from __future__ import annotations

from typing import Any

from app.db.json_utils import prepare_json_payload
from app.db.models import WebhookDelivery, WebhookSubscription, _utcnow, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteWebhookRepositoryAdapter(SqliteBaseRepository):
    """Adapter for webhook subscription and delivery operations."""

    async def async_get_user_subscriptions(
        self, user_id: int, enabled_only: bool = True
    ) -> list[dict[str, Any]]:
        """Return webhook subscriptions for a user."""

        def _get() -> list[dict[str, Any]]:
            query = WebhookSubscription.select().where(
                (WebhookSubscription.user == user_id) & (WebhookSubscription.is_deleted == False)  # noqa: E712
            )
            if enabled_only:
                query = query.where(WebhookSubscription.enabled == True)  # noqa: E712
            return [
                model_to_dict(sub) for sub in query.order_by(WebhookSubscription.created_at.desc())
            ]

        return await self._execute(_get, operation_name="get_user_subscriptions", read_only=True)

    async def async_get_subscription_by_id(self, subscription_id: int) -> dict[str, Any] | None:
        """Return a single subscription by ID."""

        def _get() -> dict[str, Any] | None:
            try:
                sub = WebhookSubscription.get_by_id(subscription_id)
                return model_to_dict(sub)
            except WebhookSubscription.DoesNotExist:
                return None

        return await self._execute(_get, operation_name="get_subscription_by_id", read_only=True)

    async def async_create_subscription(
        self,
        user_id: int,
        name: str | None,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Create a new webhook subscription."""

        def _create() -> dict[str, Any]:
            sub = WebhookSubscription.create(
                user=user_id,
                name=name,
                url=url,
                secret=secret,
                events_json=prepare_json_payload(events),
                enabled=True,
                status="active",
            )
            return model_to_dict(sub)

        return await self._execute(_create, operation_name="create_subscription")

    async def async_update_subscription(
        self, subscription_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Update an existing webhook subscription."""

        def _update() -> dict[str, Any]:
            # Translate 'events' key to 'events_json' for DB column
            update_data = dict(kwargs)
            if "events" in update_data:
                update_data["events_json"] = prepare_json_payload(update_data.pop("events"))

            (
                WebhookSubscription.update(**update_data)
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )
            sub = WebhookSubscription.get_by_id(subscription_id)
            return model_to_dict(sub)

        return await self._execute(_update, operation_name="update_subscription")

    async def async_delete_subscription(self, subscription_id: int) -> None:
        """Soft-delete a webhook subscription."""

        def _delete() -> None:
            now = _utcnow()
            (
                WebhookSubscription.update(
                    is_deleted=True,
                    deleted_at=now,
                    enabled=False,
                )
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )

        await self._execute(_delete, operation_name="delete_subscription")

    async def async_log_delivery(
        self,
        subscription_id: int,
        event_type: str,
        payload: dict[str, Any],
        response_status: int | None,
        response_body: str | None,
        duration_ms: int | None,
        success: bool,
        attempt: int,
        error: str | None,
    ) -> dict[str, Any]:
        """Persist a webhook delivery attempt."""

        def _log() -> dict[str, Any]:
            delivery = WebhookDelivery.create(
                subscription=subscription_id,
                event_type=event_type,
                payload_json=prepare_json_payload(payload),
                response_status=response_status,
                response_body=response_body,
                duration_ms=duration_ms,
                success=success,
                attempt=attempt,
                error=error,
            )
            # Update last_delivery_at on the subscription
            (
                WebhookSubscription.update(last_delivery_at=_utcnow())
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )
            return model_to_dict(delivery)

        return await self._execute(_log, operation_name="log_delivery")

    async def async_get_deliveries(
        self, subscription_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return delivery log entries for a subscription."""

        def _get() -> list[dict[str, Any]]:
            query = (
                WebhookDelivery.select()
                .where(WebhookDelivery.subscription == subscription_id)
                .order_by(WebhookDelivery.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [model_to_dict(d) for d in query]

        return await self._execute(_get, operation_name="get_deliveries", read_only=True)

    async def async_increment_failure_count(self, subscription_id: int) -> int:
        """Increment consecutive failure count. Returns the new count."""

        def _increment() -> int:
            sub = WebhookSubscription.get_by_id(subscription_id)
            new_count = (sub.failure_count or 0) + 1
            (
                WebhookSubscription.update(failure_count=new_count)
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )
            return new_count

        return await self._execute(_increment, operation_name="increment_failure_count")

    async def async_reset_failure_count(self, subscription_id: int) -> None:
        """Reset consecutive failure count to zero."""

        def _reset() -> None:
            (
                WebhookSubscription.update(failure_count=0)
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )

        await self._execute(_reset, operation_name="reset_failure_count")

    async def async_disable_subscription(self, subscription_id: int) -> None:
        """Disable a webhook subscription."""

        def _disable() -> None:
            (
                WebhookSubscription.update(status="disabled", enabled=False)
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )

        await self._execute(_disable, operation_name="disable_subscription")

    async def async_rotate_secret(self, subscription_id: int, new_secret: str) -> None:
        """Rotate the HMAC secret for a subscription."""

        def _rotate() -> None:
            (
                WebhookSubscription.update(secret=new_secret)
                .where(WebhookSubscription.id == subscription_id)
                .execute()
            )

        await self._execute(_rotate, operation_name="rotate_secret")
