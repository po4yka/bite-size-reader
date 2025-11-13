"""Use case for searching topics and finding related articles.

This use case wraps the existing TopicSearchService and provides a clean
application layer interface following the hexagonal architecture pattern.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TopicArticleDTO:
    """Data transfer object for topic article results."""

    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None


@dataclass
class SearchTopicsQuery:
    """Query for searching topics.

    This is a query object (CQRS pattern) for search operations.
    """

    topic: str
    user_id: int
    max_results: int = 5
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        """Validate query parameters."""
        if not self.topic or not self.topic.strip():
            msg = "topic must not be empty"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if self.max_results <= 0:
            msg = "max_results must be positive"
            raise ValueError(msg)
        if self.max_results > 10:
            msg = "max_results cannot exceed 10"
            raise ValueError(msg)


class SearchTopicsUseCase:
    """Use case for searching topics and discovering articles.

    This use case orchestrates the topic search workflow, including:
    - Validating search parameters
    - Delegating to search service
    - Transforming results to DTOs
    - Logging and audit trail

    Example:
        ```python
        topic_search_service = TopicSearchService(firecrawl_client, max_results=5)
        use_case = SearchTopicsUseCase(topic_search_service)

        query = SearchTopicsQuery(
            topic="machine learning",
            user_id=123,
            max_results=5,
            correlation_id="abc-123",
        )
        articles = await use_case.execute(query)
        ```

    """

    def __init__(self, topic_search_service: Any) -> None:
        """Initialize the use case.

        Args:
            topic_search_service: Service for searching topics (TopicSearchService).

        """
        self._search_service = topic_search_service

    async def execute(self, query: SearchTopicsQuery) -> list[TopicArticleDTO]:
        """Execute the topic search query.

        Args:
            query: Query parameters including topic and search options.

        Returns:
            List of TopicArticleDTO objects representing found articles.

        Raises:
            ValueError: If topic is invalid.
            Exception: If search service fails.

        """
        logger.info(
            "search_topics_started",
            extra={
                "topic": query.topic,
                "user_id": query.user_id,
                "max_results": query.max_results,
                "cid": query.correlation_id,
            },
        )

        try:
            # Delegate to search service
            articles = await self._search_service.find_articles(
                topic=query.topic,
                correlation_id=query.correlation_id,
            )

            # Convert to DTOs
            result = [
                TopicArticleDTO(
                    title=article.title,
                    url=article.url,
                    snippet=article.snippet,
                    source=article.source,
                    published_at=article.published_at,
                )
                for article in articles
            ]

            logger.info(
                "search_topics_completed",
                extra={
                    "topic": query.topic,
                    "user_id": query.user_id,
                    "count": len(result),
                    "cid": query.correlation_id,
                },
            )

            return result

        except ValueError as e:
            # Validation error from search service
            logger.warning(
                "search_topics_validation_error",
                extra={
                    "topic": query.topic,
                    "error": str(e),
                    "cid": query.correlation_id,
                },
            )
            raise

        except Exception as e:
            # Search service error
            logger.exception(
                "search_topics_failed",
                extra={
                    "topic": query.topic,
                    "error": str(e),
                    "cid": query.correlation_id,
                },
            )
            raise
