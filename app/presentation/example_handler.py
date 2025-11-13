"""Example handler showing how to use the hexagonal architecture.

This is a reference implementation demonstrating how to wire up the
presentation layer to use cases from the application layer.

DO NOT import this in production code - it's for documentation purposes only.
"""

import logging
from typing import Any

from app.application.use_cases.get_unread_summaries import (
    GetUnreadSummariesQuery,
)
from app.application.use_cases.mark_summary_as_read import (
    MarkSummaryAsReadCommand,
)
from app.application.use_cases.search_topics import SearchTopicsQuery
from app.di.container import Container
from app.domain.exceptions.domain_exceptions import InvalidStateTransitionError
from app.infrastructure.messaging.event_bus import EventBus

logger = logging.getLogger(__name__)


class ExampleCommandHandler:
    """Example command handler using hexagonal architecture.

    This handler demonstrates the pattern:
    1. Thin presentation layer
    2. Delegate to use cases
    3. Handle domain exceptions
    4. Format responses for user
    5. Publish domain events

    In real code, this would be integrated into your existing handler structure
    (e.g., CommandProcessor, MessageRouter).
    """

    def __init__(
        self,
        container: Container,
        response_formatter: Any,  # Your existing ResponseFormatter
    ) -> None:
        """Initialize the handler.

        Args:
            container: DI container with all dependencies.
            response_formatter: Formatter for sending messages to users.

        """
        self._container = container
        self._formatter = response_formatter
        self._event_bus = container.event_bus()

    # ==================== Command Handlers ====================

    async def handle_unread_command(
        self,
        message: Any,  # Telegram Message object
        user_id: int,
        chat_id: int,
    ) -> None:
        """Handle /unread command to list unread summaries.

        Example of using a query use case (CQRS read side).

        Args:
            message: Telegram message object.
            user_id: User ID from message.
            chat_id: Chat ID from message.

        """
        try:
            # 1. Create query object
            query = GetUnreadSummariesQuery(
                user_id=user_id,
                chat_id=chat_id,
                limit=10,
            )

            # 2. Get use case from container
            use_case = self._container.get_unread_summaries_use_case()

            # 3. Execute use case
            summaries = await use_case.execute(query)

            # 4. Format response for user
            if not summaries:
                await self._formatter.safe_reply(message, "You have no unread summaries.")
                return

            # Format summaries for display
            response = f"📚 You have {len(summaries)} unread summaries:\n\n"
            for i, summary in enumerate(summaries, 1):
                response += f"{i}. {summary.get_tldr()[:100]}...\n"

            await self._formatter.safe_reply(message, response)

        except ValueError as e:
            # Validation error
            await self._formatter.safe_reply(message, f"❌ Invalid request: {e}")

        except Exception as e:
            # Unexpected error
            logger.exception("handle_unread_command_failed", extra={"error": str(e)})
            await self._formatter.safe_reply(message, "❌ An error occurred. Please try again.")

    async def handle_read_command(
        self,
        message: Any,  # Telegram Message object
        summary_id: int,
        user_id: int,
    ) -> None:
        """Handle command to mark a summary as read.

        Example of using a command use case (CQRS write side) and publishing events.

        Args:
            message: Telegram message object.
            summary_id: ID of the summary to mark as read.
            user_id: User ID from message.

        """
        try:
            # 1. Create command object
            command = MarkSummaryAsReadCommand(
                summary_id=summary_id,
                user_id=user_id,
            )

            # 2. Get use case from container
            use_case = self._container.mark_summary_as_read_use_case()

            # 3. Execute use case (returns domain event)
            event = await use_case.execute(command)

            # 4. Publish domain event
            await self._event_bus.publish(event)

            # 5. Send success response
            await self._formatter.safe_reply(message, f"✅ Summary {summary_id} marked as read.")

        except ValueError as e:
            # Command validation error
            await self._formatter.safe_reply(message, f"❌ Invalid input: {e}")

        except InvalidStateTransitionError as e:
            # Domain business rule violation
            await self._formatter.safe_reply(message, f"❌ {e.message}")

        except Exception as e:
            # Unexpected error
            logger.exception("handle_read_command_failed", extra={"error": str(e)})
            await self._formatter.safe_reply(message, "❌ An error occurred. Please try again.")

    async def handle_search_command(
        self,
        message: Any,  # Telegram Message object
        topic: str,
        user_id: int,
        correlation_id: str,
    ) -> None:
        """Handle /find command to search for topic articles.

        Example of using a search use case.

        Args:
            message: Telegram message object.
            topic: Search topic.
            user_id: User ID from message.
            correlation_id: Correlation ID for tracking.

        """
        try:
            # 1. Create query object
            query = SearchTopicsQuery(
                topic=topic,
                user_id=user_id,
                max_results=5,
                correlation_id=correlation_id,
            )

            # 2. Get use case from container
            use_case = self._container.search_topics_use_case()
            if use_case is None:
                await self._formatter.safe_reply(message, "❌ Search is not configured.")
                return

            # 3. Execute use case
            articles = await use_case.execute(query)

            # 4. Format response
            if not articles:
                await self._formatter.safe_reply(message, f"No articles found for '{topic}'.")
                return

            response = f"🔍 Found {len(articles)} articles about '{topic}':\n\n"
            for i, article in enumerate(articles, 1):
                response += f"{i}. {article.title}\n"
                response += f"   {article.url}\n\n"

            await self._formatter.safe_reply(message, response)

        except ValueError as e:
            # Validation error
            await self._formatter.safe_reply(message, f"❌ Invalid search: {e}")

        except Exception as e:
            # Search service error
            logger.exception("handle_search_command_failed", extra={"error": str(e)})
            await self._formatter.safe_reply(message, "❌ Search failed. Please try again.")


# ==================== Integration Example ====================


def integrate_with_existing_code(database: Any, topic_search_service: Any) -> None:
    """Example of how to integrate the new architecture with existing code.

    This function shows the integration points between old and new code.

    Args:
        database: Your existing Database instance.
        topic_search_service: Your existing TopicSearchService instance.

    """
    # 1. Create the DI container
    container = Container(
        database=database,
        topic_search_service=topic_search_service,
    )

    # 2. Wire up event handlers (optional)
    container.wire_event_handlers()

    # 3. Create handler with container
    # response_formatter = YourExistingResponseFormatter(...)
    # handler = ExampleCommandHandler(container, response_formatter)

    # 4. Use in your existing routing
    # In MessageRouter._route_message_content() or CommandProcessor:
    #
    # if text.startswith("/unread"):
    #     await handler.handle_unread_command(message, uid, cid)
    #     return
    #
    # if text.startswith("/read"):
    #     summary_id = extract_summary_id(text)
    #     await handler.handle_read_command(message, summary_id, uid)
    #     return

    # 5. You can still use old code alongside new code
    # The container wraps the existing Database, so both approaches work together


# ==================== Event Handler Example ====================


def example_event_handlers(event_bus: EventBus) -> None:
    """Example event handlers showing loose coupling through events.

    These handlers respond to domain events without tight coupling to
    the use cases that emit them.
    """
    from app.domain.events.summary_events import SummaryMarkedAsRead

    # Example: Log when summary is marked as read
    async def on_summary_marked_as_read(event: SummaryMarkedAsRead) -> None:
        logger.info(
            "summary_marked_as_read_event",
            extra={
                "summary_id": event.summary_id,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

    # Example: Update search index when summary is marked as read
    async def update_search_index(event: SummaryMarkedAsRead) -> None:
        # Update FTS index, update caches, etc.
        logger.debug(f"Updating search index for summary {event.summary_id}")

    # Example: Send analytics event
    async def track_analytics(event: SummaryMarkedAsRead) -> None:
        # Send to analytics service
        logger.debug(f"Tracking read event for summary {event.summary_id}")

    # Subscribe all handlers
    event_bus.subscribe(SummaryMarkedAsRead, on_summary_marked_as_read)
    event_bus.subscribe(SummaryMarkedAsRead, update_search_index)
    event_bus.subscribe(SummaryMarkedAsRead, track_analytics)

    # Now when the event is published, all three handlers are called
