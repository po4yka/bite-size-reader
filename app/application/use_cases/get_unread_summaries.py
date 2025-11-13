"""Use case for retrieving unread summaries.

This is a query use case following the CQRS pattern - it only reads data
and does not modify state.
"""

import logging
from dataclasses import dataclass

from app.domain.models.summary import Summary
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = logging.getLogger(__name__)


@dataclass
class GetUnreadSummariesQuery:
    """Query for retrieving unread summaries.

    This is a query object (CQRS pattern) for read operations.
    """

    user_id: int
    chat_id: int
    limit: int = 10
    topic: str | None = None

    def __post_init__(self) -> None:
        """Validate query parameters."""
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if self.chat_id <= 0:
            msg = "chat_id must be positive"
            raise ValueError(msg)
        if self.limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        if self.limit > 100:
            msg = "limit cannot exceed 100"
            raise ValueError(msg)
        if self.topic is not None and not self.topic.strip():
            msg = "topic cannot be empty string"
            raise ValueError(msg)


class GetUnreadSummariesUseCase:
    """Use case for retrieving unread summaries for a user.

    This is a read-only query use case that demonstrates the CQRS pattern
    where queries are separated from commands.

    Example:
        ```python
        repository = SqliteSummaryRepositoryAdapter(database)
        use_case = GetUnreadSummariesUseCase(repository)

        query = GetUnreadSummariesQuery(user_id=123, chat_id=456, limit=10)
        summaries = await use_case.execute(query)
        ```

    """

    def __init__(self, summary_repository: SqliteSummaryRepositoryAdapter) -> None:
        """Initialize the use case.

        Args:
            summary_repository: Repository for summary queries.

        """
        self._summary_repo = summary_repository

    async def execute(self, query: GetUnreadSummariesQuery) -> list[Summary]:
        """Execute the query to get unread summaries.

        Args:
            query: Query parameters including user ID, chat ID, limit, and optional topic filter.

        Returns:
            List of unread Summary domain models.

        """
        logger.info(
            "get_unread_summaries_started",
            extra={
                "user_id": query.user_id,
                "chat_id": query.chat_id,
                "limit": query.limit,
                "topic": query.topic,
            },
        )

        # Query repository
        db_summaries = await self._summary_repo.async_get_unread_summaries(
            uid=query.user_id,
            cid=query.chat_id,
            limit=query.limit,
            topic=query.topic,
        )

        # Convert to domain models
        summaries = [
            self._summary_repo.to_domain_model(db_summary)
            for db_summary in db_summaries
        ]

        logger.info(
            "get_unread_summaries_completed",
            extra={
                "user_id": query.user_id,
                "chat_id": query.chat_id,
                "topic": query.topic,
                "count": len(summaries),
            },
        )

        return summaries
