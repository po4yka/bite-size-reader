"""Dependency injection container for wiring components.

This container provides a centralized place to configure and wire all
dependencies for the hexagonal architecture.
"""

from typing import Any

from app.application.use_cases.get_unread_summaries import GetUnreadSummariesUseCase
from app.application.use_cases.mark_summary_as_read import MarkSummaryAsReadUseCase
from app.application.use_cases.mark_summary_as_unread import MarkSummaryAsUnreadUseCase
from app.application.use_cases.search_topics import SearchTopicsUseCase
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)


class Container:
    """Dependency injection container.

    This container manages the lifecycle and wiring of all application components.
    It follows the principle of dependency inversion by creating concrete
    implementations and injecting them into use cases.

    Example:
        ```python
        # Initialize container with database
        container = Container(database)

        # Get use cases
        get_summaries = container.get_unread_summaries_use_case()
        mark_as_read = container.mark_summary_as_read_use_case()

        # Use in handlers
        query = GetUnreadSummariesQuery(user_id=123, chat_id=456)
        summaries = await get_summaries.execute(query)
        ```
    """

    def __init__(
        self,
        database: Any,
        topic_search_service: Any | None = None,
    ) -> None:
        """Initialize the container.

        Args:
            database: The Database instance (existing infrastructure).
            topic_search_service: Optional TopicSearchService for search use case.
        """
        self._database = database
        self._topic_search_service = topic_search_service

        # Lazy-initialized components
        self._event_bus: EventBus | None = None
        self._summary_repo: SqliteSummaryRepositoryAdapter | None = None
        self._request_repo: SqliteRequestRepositoryAdapter | None = None
        self._crawl_result_repo: SqliteCrawlResultRepositoryAdapter | None = None

        # Lazy-initialized use cases
        self._get_unread_summaries_use_case: GetUnreadSummariesUseCase | None = None
        self._mark_summary_as_read_use_case: MarkSummaryAsReadUseCase | None = None
        self._mark_summary_as_unread_use_case: MarkSummaryAsUnreadUseCase | None = None
        self._search_topics_use_case: SearchTopicsUseCase | None = None

    # ==================== Infrastructure Layer ====================

    def event_bus(self) -> EventBus:
        """Get or create the event bus.

        Returns:
            Singleton EventBus instance.
        """
        if self._event_bus is None:
            self._event_bus = EventBus()
        return self._event_bus

    def summary_repository(self) -> SqliteSummaryRepositoryAdapter:
        """Get or create the summary repository.

        Returns:
            Summary repository adapter wrapping the database.
        """
        if self._summary_repo is None:
            self._summary_repo = SqliteSummaryRepositoryAdapter(self._database)
        return self._summary_repo

    def request_repository(self) -> SqliteRequestRepositoryAdapter:
        """Get or create the request repository.

        Returns:
            Request repository adapter wrapping the database.
        """
        if self._request_repo is None:
            self._request_repo = SqliteRequestRepositoryAdapter(self._database)
        return self._request_repo

    def crawl_result_repository(self) -> SqliteCrawlResultRepositoryAdapter:
        """Get or create the crawl result repository.

        Returns:
            Crawl result repository adapter wrapping the database.
        """
        if self._crawl_result_repo is None:
            self._crawl_result_repo = SqliteCrawlResultRepositoryAdapter(self._database)
        return self._crawl_result_repo

    # ==================== Application Layer (Use Cases) ====================

    def get_unread_summaries_use_case(self) -> GetUnreadSummariesUseCase:
        """Get or create the GetUnreadSummariesUseCase.

        Returns:
            Use case for querying unread summaries.
        """
        if self._get_unread_summaries_use_case is None:
            self._get_unread_summaries_use_case = GetUnreadSummariesUseCase(
                summary_repository=self.summary_repository()
            )
        return self._get_unread_summaries_use_case

    def mark_summary_as_read_use_case(self) -> MarkSummaryAsReadUseCase:
        """Get or create the MarkSummaryAsReadUseCase.

        Returns:
            Use case for marking summaries as read.
        """
        if self._mark_summary_as_read_use_case is None:
            self._mark_summary_as_read_use_case = MarkSummaryAsReadUseCase(
                summary_repository=self.summary_repository()
            )
        return self._mark_summary_as_read_use_case

    def mark_summary_as_unread_use_case(self) -> MarkSummaryAsUnreadUseCase:
        """Get or create the MarkSummaryAsUnreadUseCase.

        Returns:
            Use case for marking summaries as unread.
        """
        if self._mark_summary_as_unread_use_case is None:
            self._mark_summary_as_unread_use_case = MarkSummaryAsUnreadUseCase(
                summary_repository=self.summary_repository()
            )
        return self._mark_summary_as_unread_use_case

    def search_topics_use_case(self) -> SearchTopicsUseCase | None:
        """Get or create the SearchTopicsUseCase.

        Returns:
            Use case for searching topics, or None if topic search service not configured.
        """
        if self._topic_search_service is None:
            return None

        if self._search_topics_use_case is None:
            self._search_topics_use_case = SearchTopicsUseCase(
                topic_search_service=self._topic_search_service
            )
        return self._search_topics_use_case

    # ==================== Helper Methods ====================

    def wire_event_handlers(self) -> None:
        """Wire up event handlers to the event bus.

        This method shows how to subscribe handlers to domain events.
        Add your event handlers here.

        Example:
            ```python
            async def on_summary_created(event: SummaryCreated):
                # Send notification, update search index, etc.
                pass

            event_bus = self.event_bus()
            event_bus.subscribe(SummaryCreated, on_summary_created)
            ```
        """
        # TODO: Add event handler subscriptions here
        # Example:
        # from app.domain.events.summary_events import SummaryMarkedAsRead
        #
        # async def on_summary_marked_as_read(event: SummaryMarkedAsRead):
        #     logger.info(f"Summary {event.summary_id} was marked as read")
        #
        # self.event_bus().subscribe(SummaryMarkedAsRead, on_summary_marked_as_read)
        pass
