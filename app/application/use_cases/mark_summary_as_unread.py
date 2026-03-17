"""Use case for marking a summary as unread.

This use case demonstrates the hexagonal architecture pattern and complements
the MarkSummaryAsReadUseCase.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.application.ports import SummaryRepositoryPort
from app.application.use_cases.summary_fetch import fetch_summary_or_raise
from app.core.time_utils import UTC
from app.domain.events.summary_events import SummaryMarkedAsUnread
from app.domain.exceptions.domain_exceptions import (
    InvalidStateTransitionError,
)
from app.domain.services.summary_validator import SummaryValidator

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
        repository = your_summary_repository_adapter
        use_case = MarkSummaryAsUnreadUseCase(repository)

        command = MarkSummaryAsUnreadCommand(summary_id=123, user_id=456)
        event = await use_case.execute(command)
        ```

    """

    def __init__(self, summary_repository: SummaryRepositoryPort) -> None:
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

        # 1. Fetch summary from repository
        summary_data = await fetch_summary_or_raise(self._summary_repo, command.summary_id)

        # 2. Convert to domain model
        summary = self._summary_repo.to_domain_model(summary_data)

        # 3. Validate that the transition is allowed
        can_mark, reason = SummaryValidator.can_mark_as_unread(summary)
        if not can_mark:
            logger.warning(
                "mark_summary_as_unread_rejected",
                extra={
                    "summary_id": command.summary_id,
                    "reason": reason,
                    "is_read": summary.is_read,
                },
            )
            msg = f"Cannot mark summary as unread: {reason}"
            raise InvalidStateTransitionError(
                msg,
                details={
                    "summary_id": command.summary_id,
                    "current_state": "read" if summary.is_read else "unread",
                },
            )

        # 4. Perform the state transition (domain logic)
        try:
            summary.mark_as_unread()
        except ValueError as e:
            # Domain model raised validation error
            logger.exception(
                "mark_summary_as_unread_domain_error",
                extra={"summary_id": command.summary_id, "error": str(e)},
            )
            raise InvalidStateTransitionError(
                str(e),
                details={"summary_id": command.summary_id},
            ) from e

        # 5. Persist the changes
        await self._summary_repo.async_mark_summary_as_unread(command.summary_id)

        # 6. Create and return domain event
        event = SummaryMarkedAsUnread(
            occurred_at=datetime.now(UTC),
            aggregate_id=command.summary_id,
            summary_id=command.summary_id,
        )

        logger.info(
            "mark_summary_as_unread_completed",
            extra={"summary_id": command.summary_id, "user_id": command.user_id},
        )

        return event
