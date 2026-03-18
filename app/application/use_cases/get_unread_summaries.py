"""Use case for retrieving unread summaries."""

import logging
from dataclasses import dataclass

from app.application.ports import SummaryRepositoryPort
from app.domain.models.summary import Summary, summary_from_dict

logger = logging.getLogger(__name__)


@dataclass
class GetUnreadSummariesQuery:
    """Query for retrieving unread summaries."""

    user_id: int
    chat_id: int
    limit: int = 10
    topic: str | None = None

    def __post_init__(self) -> None:
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
    """Use case for retrieving unread summaries for a user."""

    def __init__(self, summary_repository: SummaryRepositoryPort) -> None:
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

        db_summaries = await self._summary_repo.async_get_unread_summaries(
            user_id=query.user_id,
            chat_id=query.chat_id,
            limit=query.limit,
            topic=query.topic,
        )

        summaries = [summary_from_dict(db_summary) for db_summary in db_summaries]

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
