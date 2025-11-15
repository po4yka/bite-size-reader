"""Simple in-memory event bus for domain events.

This event bus allows decoupling between event publishers and subscribers.
It follows the Observer pattern and enables loose coupling for side effects.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar

from app.domain.events.summary_events import DomainEvent

logger = logging.getLogger(__name__)

# Type variable for domain events
TEvent = TypeVar("TEvent", bound=DomainEvent)

# Event handler type - async function that takes an event and returns None
EventHandler = Callable[[TEvent], Awaitable[None]]


class EventBus:
    """Simple in-memory event bus for domain events.

    This event bus allows components to subscribe to domain events and
    publish events without tight coupling. Handlers are called asynchronously.

    Example:
        ```python
        event_bus = EventBus()

        # Subscribe to events
        async def on_summary_created(event: SummaryCreated):
            print(f"Summary {event.summary_id} was created!")

        event_bus.subscribe(SummaryCreated, on_summary_created)

        # Publish events
        event = SummaryCreated(
            occurred_at=datetime.now(timezone.utc),
            summary_id=123,
            request_id=456,
            language="en",
            has_insights=False,
        )
        await event_bus.publish(event)
        ```

    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        # Map event type to list of handlers
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[TEvent],
        handler: EventHandler[TEvent],
    ) -> None:
        """Subscribe a handler to a specific event type.

        Args:
            event_type: The type of event to subscribe to (e.g., SummaryCreated).
            handler: Async function to call when event is published.

        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "event_handler_subscribed",
            extra={
                "event_type": event_type.__name__,
                "handler": handler.__name__,
                "total_handlers": len(self._handlers[event_type]),
            },
        )

    def unsubscribe(
        self,
        event_type: type[TEvent],
        handler: EventHandler[TEvent],
    ) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: The type of event to unsubscribe from.
            handler: The handler function to remove.

        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(
                    "event_handler_unsubscribed",
                    extra={
                        "event_type": event_type.__name__,
                        "handler": handler.__name__,
                    },
                )
            except ValueError:
                logger.warning(
                    "event_handler_not_found",
                    extra={
                        "event_type": event_type.__name__,
                        "handler": handler.__name__,
                    },
                )

    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all subscribed handlers.

        Handlers are called asynchronously. If a handler fails, the error is
        logged but other handlers continue to execute.

        Args:
            event: The domain event to publish.

        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(
                "event_published_no_handlers",
                extra={
                    "event_type": event_type.__name__,
                    "event_id": getattr(event, "aggregate_id", None),
                },
            )
            return

        logger.info(
            "event_published",
            extra={
                "event_type": event_type.__name__,
                "event_id": getattr(event, "aggregate_id", None),
                "handler_count": len(handlers),
            },
        )

        # Call all handlers asynchronously
        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                # Log error but continue with other handlers
                logger.exception(
                    "event_handler_failed",
                    extra={
                        "event_type": event_type.__name__,
                        "handler": handler.__name__,
                        "error": str(exc),
                    },
                )

    def clear_handlers(self, event_type: type[TEvent] | None = None) -> None:
        """Clear handlers for a specific event type or all handlers.

        Args:
            event_type: If provided, clear handlers for this event type only.
                       If None, clear all handlers.

        """
        if event_type is not None:
            if event_type in self._handlers:
                count = len(self._handlers[event_type])
                del self._handlers[event_type]
                logger.debug(
                    "event_handlers_cleared",
                    extra={"event_type": event_type.__name__, "count": count},
                )
        else:
            total_handlers = sum(len(handlers) for handlers in self._handlers.values())
            self._handlers.clear()
            logger.debug(
                "all_event_handlers_cleared",
                extra={"total_handlers": total_handlers},
            )

    def get_handler_count(self, event_type: type[TEvent]) -> int:
        """Get the number of handlers subscribed to an event type.

        Args:
            event_type: The event type to query.

        Returns:
            Number of handlers subscribed to this event type.

        """
        return len(self._handlers.get(event_type, []))

    def get_all_event_types(self) -> list[type]:
        """Get list of all event types that have subscribers.

        Returns:
            List of event types with at least one subscriber.

        """
        return list(self._handlers.keys())
