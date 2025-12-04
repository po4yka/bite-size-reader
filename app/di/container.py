"""Dependency injection container for wiring components.

This container provides a centralized place to configure and wire all
dependencies for the hexagonal architecture.
"""

from typing import Any

from app.application.use_cases.get_unread_summaries import GetUnreadSummariesUseCase
from app.application.use_cases.mark_summary_as_read import MarkSummaryAsReadUseCase
from app.application.use_cases.mark_summary_as_unread import MarkSummaryAsUnreadUseCase
from app.application.use_cases.search_topics import SearchTopicsUseCase
from app.application.use_cases.summarize_url import SummarizeUrlUseCase
from app.domain.services.summary_validator import SummaryValidator
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.event_handlers import wire_event_handlers
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
        content_fetcher: Any | None = None,
        llm_client: Any | None = None,
        analytics_service: Any | None = None,
        telegram_client: Any | None = None,
        notification_service: Any | None = None,
        cache_service: Any | None = None,
        webhook_client: Any | None = None,
        webhook_url: str | None = None,
        vector_store: Any | None = None,
        embedding_generator: Any | None = None,
    ) -> None:
        """Initialize the container.

        Args:
            database: The Database instance (existing infrastructure).
            topic_search_service: Optional TopicSearchService for search use case.
            content_fetcher: Optional content fetcher service (e.g., FirecrawlClient).
            llm_client: Optional LLM client (e.g., OpenRouterClient).
            analytics_service: Optional analytics service client.
            telegram_client: Optional Telegram client for notifications.
            notification_service: Optional notification service for other channels.
            cache_service: Optional cache service (Redis, Memcached, etc.).
            webhook_client: Optional HTTP client for sending webhooks.
            webhook_url: Optional webhook URL to send events to.

        """
        self._database = database
        self._topic_search_service = topic_search_service
        self._content_fetcher = content_fetcher
        self._llm_client = llm_client
        self._analytics_service = analytics_service
        self._telegram_client = telegram_client
        self._notification_service = notification_service
        self._cache_service = cache_service
        self._webhook_client = webhook_client
        self._webhook_url = webhook_url
        self._vector_store = vector_store
        self._embedding_generator = embedding_generator

        # Lazy-initialized components
        self._event_bus: EventBus | None = None
        self._summary_repo: SqliteSummaryRepositoryAdapter | None = None
        self._request_repo: SqliteRequestRepositoryAdapter | None = None
        self._crawl_result_repo: SqliteCrawlResultRepositoryAdapter | None = None
        self._summary_validator: SummaryValidator | None = None

        # Lazy-initialized use cases
        self._get_unread_summaries_use_case: GetUnreadSummariesUseCase | None = None
        self._mark_summary_as_read_use_case: MarkSummaryAsReadUseCase | None = None
        self._mark_summary_as_unread_use_case: MarkSummaryAsUnreadUseCase | None = None
        self._search_topics_use_case: SearchTopicsUseCase | None = None
        self._summarize_url_use_case: SummarizeUrlUseCase | None = None

    def event_bus(self) -> EventBus:
        """Get or create the event bus.

        Returns:
            Singleton EventBus instance.

        """
        if self._event_bus is None:
            self._event_bus = EventBus()
        return self._event_bus

    def vector_store(self) -> Any | None:
        """Get the configured vector store if available."""

        return self._vector_store

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

    def summary_validator(self) -> SummaryValidator:
        """Get or create the summary validator.

        Returns:
            SummaryValidator domain service.

        """
        if self._summary_validator is None:
            self._summary_validator = SummaryValidator()
        return self._summary_validator

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

    def summarize_url_use_case(self) -> SummarizeUrlUseCase | None:
        """Get or create the SummarizeUrlUseCase.

        Returns:
            Use case for summarizing URLs, or None if required services not configured.

        """
        if self._content_fetcher is None or self._llm_client is None:
            return None

        if self._summarize_url_use_case is None:
            self._summarize_url_use_case = SummarizeUrlUseCase(
                request_repository=self.request_repository(),
                summary_repository=self.summary_repository(),
                crawl_result_repository=self.crawl_result_repository(),
                content_fetcher=self._content_fetcher,
                llm_client=self._llm_client,
                summary_validator=self.summary_validator(),
            )
        return self._summarize_url_use_case

    def wire_event_handlers_auto(self) -> None:
        """Wire up event handlers to the event bus automatically.

        This method uses the event_handlers module to subscribe all
        event handlers to their respective events.

        Call this during application initialization to enable side effects
        like search indexing, analytics, audit logging, notifications,
        cache invalidation, and webhooks.

        Example:
            ```python
            container = Container(database, ...)
            container.wire_event_handlers_auto()
            # Now all events will be handled automatically
            ```

        """
        wire_event_handlers(
            event_bus=self.event_bus(),
            database=self._database,
            analytics_service=self._analytics_service,
            telegram_client=self._telegram_client,
            notification_service=self._notification_service,
            cache_service=self._cache_service,
            webhook_client=self._webhook_client,
            webhook_url=self._webhook_url,
            embedding_generator=self._embedding_generator,
            vector_store=self._vector_store,
        )
