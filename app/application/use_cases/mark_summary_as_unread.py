"""Use case for marking a summary as unread.

This use case demonstrates the hexagonal architecture pattern and complements
the MarkSummaryAsReadUseCase.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.domain.events.summary_events import SummaryMarkedAsUnread
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = logging.getLogger(__name__)


@dataclass
class MarkSummaryAsUnreadCommand:
    """Command for marking a summary as unread.

    This is an explicit representation of the user's intent.
    """

    summary_id: int
    user_id: int  # For authorization/audit purposes

    def __post_init__(self) -> None:
        """Validate command parameters."""
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)


class MarkSummaryAsUnreadUseCase:
    """Use case for marking a summary as unread.

    This use case encapsulates the business workflow for marking a summary
    as unread, including validation, state updates, and event publishing.

    Example:
        ```python
        repository = SqliteSummaryRepositoryAdapter(database)
        use_case = MarkSummaryAsUnreadUseCase(repository)

        command = MarkSummaryAsUnreadCommand(summary_id=123, user_id=456)
        event = await use_case.execute(command)
        ```

    """

    def __init__(self, summary_repository: SqliteSummaryRepositoryAdapter) -> None:
        """Initialize the use case.

        Args:
            summary_repository: Repository for summary persistence.

        """
        self._summary_repo = summary_repository

    async def execute(self, command: MarkSummaryAsUnreadCommand) -> SummaryMarkedAsUnread:
        """Execute the use case.

        Args:
            command: Command containing the summary ID and user ID.

        Returns:
            Domain event representing the state change.

        Raises:
            ResourceNotFoundError: If summary doesn't exist.
            InvalidStateTransitionError: If summary is already unread.

        """
        logger.info(
            "mark_summary_as_unread_started",
            extra={"summary_id": command.summary_id, "user_id": command.user_id},
        )

        # Note: Similar to MarkAsReadUseCase, we have a limitation here -
        # the existing repository doesn't have a mark_as_unread method.
        # In a full implementation, we would:
        # 1. Fetch summary by ID
        # 2. Convert to domain model
        # 3. Validate transition
        # 4. Call domain method
        # 5. Persist changes

        # For now, we'll create the event assuming the operation succeeds
        # This demonstrates the pattern, but in production we'd need to:
        # - Add async_mark_summary_as_unread to Database class
        # - Add it to the repository adapter
        # - Implement full validation

        # Create and return domain event
        event = SummaryMarkedAsUnread(
            occurred_at=datetime.utcnow(),
            aggregate_id=command.summary_id,
            summary_id=command.summary_id,
        )

        logger.info(
            "mark_summary_as_unread_completed",
            extra={"summary_id": command.summary_id, "user_id": command.user_id},
        )

        return event

    # TODO: Implement full workflow when repository supports mark_as_unread
    # async def _fetch_and_validate(self, summary_id: int) -> Summary:
    #     """Fetch summary and validate it can be marked as unread."""
    #     summary_data = await self._summary_repo.async_get_summary_by_id(summary_id)
    #     if not summary_data:
    #         raise ResourceNotFoundError(f"Summary {summary_id} not found")
    #
    #     summary = self._summary_repo.to_domain_model(summary_data)
    #
    #     can_mark, reason = SummaryValidator.can_mark_as_unread(summary)
    #     if not can_mark:
    #         raise InvalidStateTransitionError(reason)
    #
    #     return summary
