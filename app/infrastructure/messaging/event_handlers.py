"""Real event handlers for domain events.

These handlers demonstrate how to use the event bus to implement side effects
and cross-cutting concerns in a decoupled way.
"""

import logging
from typing import Any

from app.domain.events.request_events import RequestCompleted, RequestFailed
from app.domain.events.summary_events import SummaryCreated, SummaryMarkedAsRead

logger = logging.getLogger(__name__)


class SearchIndexEventHandler:
    """Event handler for updating the full-text search index.

    This handler responds to summary-related events and updates the FTS index
    to keep search functionality in sync with the database.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the handler.

        Args:
            database: Database instance with FTS methods.
        """
        self._db = database

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Update search index when a new summary is created.

        Args:
            event: SummaryCreated domain event.
        """
        logger.info(
            "updating_search_index_for_new_summary",
            extra={
                "summary_id": event.summary_id,
                "request_id": event.request_id,
                "language": event.language,
            },
        )

        try:
            # Rebuild search index for this request
            # This ensures the new summary is searchable
            await self._db.async_rebuild_topic_index_for_request(event.request_id)

            logger.debug(
                "search_index_updated",
                extra={"request_id": event.request_id, "summary_id": event.summary_id},
            )

        except Exception as e:  # noqa: BLE001
            # Log error but don't fail - search index update is not critical
            logger.exception(
                "search_index_update_failed",
                extra={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "error": str(e),
                },
            )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        """Handle search index when summary is marked as read.

        Could be used to deprioritize read summaries in search results.

        Args:
            event: SummaryMarkedAsRead domain event.
        """
        logger.debug(
            "summary_marked_as_read_event",
            extra={"summary_id": event.summary_id},
        )

        # Optional: Update search index to deprioritize read summaries
        # For now, just log the event


class AnalyticsEventHandler:
    """Event handler for tracking analytics.

    This handler responds to various events and sends analytics data
    to external analytics services.
    """

    def __init__(self, analytics_service: Any | None = None) -> None:
        """Initialize the handler.

        Args:
            analytics_service: Optional analytics service client.
        """
        self._analytics = analytics_service

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Track successful request completion.

        Args:
            event: RequestCompleted domain event.
        """
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
                # Send to analytics service
                await self._analytics.track(
                    "request_completed",
                    {
                        "request_id": event.request_id,
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_completed", "error": str(e)},
                )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Track failed requests.

        Args:
            event: RequestFailed domain event.
        """
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
                # Send to analytics service
                await self._analytics.track(
                    "request_failed",
                    {
                        "request_id": event.request_id,
                        "error_message": event.error_message,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "request_failed", "error": str(e)},
                )

    async def on_summary_marked_as_read(self, event: SummaryMarkedAsRead) -> None:
        """Track when users mark summaries as read.

        Args:
            event: SummaryMarkedAsRead domain event.
        """
        logger.debug(
            "summary_read_analytics",
            extra={"summary_id": event.summary_id},
        )

        if self._analytics:
            try:
                await self._analytics.track(
                    "summary_marked_as_read",
                    {
                        "summary_id": event.summary_id,
                        "timestamp": event.occurred_at.isoformat(),
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "analytics_tracking_failed",
                    extra={"event": "summary_marked_as_read", "error": str(e)},
                )


class AuditLogEventHandler:
    """Event handler for comprehensive audit logging.

    This handler logs all domain events to the audit log for compliance
    and debugging purposes.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the handler.

        Args:
            database: Database instance with audit log methods.
        """
        self._db = database

    async def on_summary_created(self, event: SummaryCreated) -> None:
        """Audit log summary creation.

        Args:
            event: SummaryCreated domain event.
        """
        try:
            await self._db.async_insert_audit_log(
                log_level="INFO",
                event_type="summary_created",
                details={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "language": event.language,
                    "has_insights": event.has_insights,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "summary_created", "error": str(e)},
            )

    async def on_request_completed(self, event: RequestCompleted) -> None:
        """Audit log request completion.

        Args:
            event: RequestCompleted domain event.
        """
        try:
            await self._db.async_insert_audit_log(
                log_level="INFO",
                event_type="request_completed",
                details={
                    "request_id": event.request_id,
                    "summary_id": event.summary_id,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "request_completed", "error": str(e)},
            )

    async def on_request_failed(self, event: RequestFailed) -> None:
        """Audit log request failure.

        Args:
            event: RequestFailed domain event.
        """
        try:
            await self._db.async_insert_audit_log(
                log_level="ERROR",
                event_type="request_failed",
                details={
                    "request_id": event.request_id,
                    "error_message": event.error_message,
                    "error_details": event.error_details,
                    "timestamp": event.occurred_at.isoformat(),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "audit_log_failed",
                extra={"event_type": "request_failed", "error": str(e)},
            )


def wire_event_handlers(event_bus: Any, database: Any, analytics_service: Any | None = None) -> None:
    """Wire up all event handlers to the event bus.

    This function subscribes all event handlers to their respective events.
    Call this during application initialization.

    Args:
        event_bus: The EventBus instance.
        database: Database instance for handlers that need it.
        analytics_service: Optional analytics service client.

    Example:
        ```python
        from app.infrastructure.messaging.event_bus import EventBus
        from app.infrastructure.messaging.event_handlers import wire_event_handlers

        event_bus = EventBus()
        wire_event_handlers(event_bus, database, analytics_service)

        # Now when events are published, all handlers are called
        await event_bus.publish(SummaryCreated(...))
        ```
    """
    # Create handler instances
    search_index_handler = SearchIndexEventHandler(database)
    analytics_handler = AnalyticsEventHandler(analytics_service)
    audit_log_handler = AuditLogEventHandler(database)

    # Wire up summary events
    event_bus.subscribe(SummaryCreated, search_index_handler.on_summary_created)
    event_bus.subscribe(SummaryCreated, audit_log_handler.on_summary_created)

    event_bus.subscribe(
        SummaryMarkedAsRead, search_index_handler.on_summary_marked_as_read
    )
    event_bus.subscribe(
        SummaryMarkedAsRead, analytics_handler.on_summary_marked_as_read
    )

    # Wire up request events
    event_bus.subscribe(RequestCompleted, analytics_handler.on_request_completed)
    event_bus.subscribe(RequestCompleted, audit_log_handler.on_request_completed)

    event_bus.subscribe(RequestFailed, analytics_handler.on_request_failed)
    event_bus.subscribe(RequestFailed, audit_log_handler.on_request_failed)

    logger.info(
        "event_handlers_wired",
        extra={
            "summary_created_handlers": event_bus.get_handler_count(SummaryCreated),
            "summary_read_handlers": event_bus.get_handler_count(SummaryMarkedAsRead),
            "request_completed_handlers": event_bus.get_handler_count(RequestCompleted),
            "request_failed_handlers": event_bus.get_handler_count(RequestFailed),
        },
    )
