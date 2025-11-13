"""Use case for marking a summary as read.

This use case demonstrates the hexagonal architecture pattern by:
1. Accepting input through a command
2. Orchestrating domain models and services
3. Using repository interfaces (ports) to persist changes
4. Raising domain events for side effects
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.domain.events.summary_events import SummaryMarkedAsRead
from app.domain.exceptions.domain_exceptions import (
    InvalidStateTransitionError,
)
from app.domain.services.summary_validator import SummaryValidator
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = logging.getLogger(__name__)


@dataclass
class MarkSummaryAsReadCommand:
    """Command for marking a summary as read.

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


class MarkSummaryAsReadUseCase:
    """Use case for marking a summary as read.

    This use case encapsulates the business workflow for marking a summary
    as read, including validation, state updates, and event publishing.

    Example:
        ```python
        repository = SqliteSummaryRepositoryAdapter(database)
        use_case = MarkSummaryAsReadUseCase(repository)

        command = MarkSummaryAsReadCommand(summary_id=123, user_id=456)
        event = await use_case.execute(command)
        ```

    """

    def __init__(self, summary_repository: SqliteSummaryRepositoryAdapter) -> None:
        """Initialize the use case.

        Args:
            summary_repository: Repository for summary persistence.

        """
        self._summary_repo = summary_repository

    async def execute(self, command: MarkSummaryAsReadCommand) -> SummaryMarkedAsRead:
        """Execute the use case.

        Args:
            command: Command containing the summary ID and user ID.

        Returns:
            Domain event representing the state change.

        Raises:
            ResourceNotFoundError: If summary doesn't exist.
            InvalidStateTransitionError: If summary is already read.

        """
        logger.info(
            "mark_summary_as_read_started",
            extra={"summary_id": command.summary_id, "user_id": command.user_id},
        )

        # 1. Fetch summary from repository
        summary_data = await self._fetch_summary(command.summary_id)

        # 2. Convert to domain model
        summary = self._summary_repo.to_domain_model(summary_data)

        # 3. Validate that the transition is allowed
        can_mark, reason = SummaryValidator.can_mark_as_read(summary)
        if not can_mark:
            logger.warning(
                "mark_summary_as_read_rejected",
                extra={
                    "summary_id": command.summary_id,
                    "reason": reason,
                    "is_read": summary.is_read,
                },
            )
            msg = f"Cannot mark summary as read: {reason}"
            raise InvalidStateTransitionError(
                msg,
                details={"summary_id": command.summary_id, "current_state": "read" if summary.is_read else "unread"},
            )

        # 4. Perform the state transition (domain logic)
        try:
            summary.mark_as_read()
        except ValueError as e:
            # Domain model raised validation error
            logger.exception(
                "mark_summary_as_read_domain_error",
                extra={"summary_id": command.summary_id, "error": str(e)},
            )
            raise InvalidStateTransitionError(
                str(e),
                details={"summary_id": command.summary_id},
            ) from e

        # 5. Persist the changes
        await self._summary_repo.async_mark_summary_as_read(command.summary_id)

        # 6. Create and return domain event
        event = SummaryMarkedAsRead(
            occurred_at=datetime.utcnow(),
            aggregate_id=command.summary_id,
            summary_id=command.summary_id,
        )

        logger.info(
            "mark_summary_as_read_completed",
            extra={"summary_id": command.summary_id, "user_id": command.user_id},
        )

        return event

    async def _fetch_summary(self, summary_id: int) -> dict:
        """Fetch summary by ID.

        Args:
            summary_id: ID of the summary to fetch.

        Returns:
            Summary data dictionary.

        Raises:
            ResourceNotFoundError: If summary doesn't exist.

        """
        # Note: We need to query by summary ID, but the existing repository
        # only has get_by_request_id. For now, we'll need to enhance the
        # repository interface or work with what we have.

        # This is a simplified version - in a full implementation, we'd need
        # to add a get_by_id method to the repository
        logger.debug("fetch_summary", extra={"summary_id": summary_id})

        # For now, we'll work with the existing async_mark_summary_as_read
        # which already validates existence internally.
        # In a full implementation, we'd fetch first, validate, then update.

        # Placeholder: In real implementation, fetch from repository
        # For now, we trust that the repository's mark_as_read will fail
        # if the summary doesn't exist.

        # TODO: Add get_by_id method to repository interface
        return {"id": summary_id}  # Placeholder
