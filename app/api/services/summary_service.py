"""Summary service - business logic for summary operations."""

from typing import Any

from app.api.exceptions import ResourceNotFoundError
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = get_logger(__name__)


class SummaryService:
    """Service for summary-related business logic."""

    @staticmethod
    async def get_user_summaries(
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        lang: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[dict[str, Any]], int, int]:
        """
        Get paginated summaries for a user with filtering.

        Args:
            user_id: User ID for authorization
            limit: Maximum results to return
            offset: Results offset for pagination
            is_read: Filter by read status (None = all)
            is_favorited: Filter by favorite status (None = all)
            lang: Filter by language
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            sort: Sort order (created_at_desc or created_at_asc)

        Returns:
            Tuple of (summaries list, total count, unread count)

        Raises:
            ValueError: If invalid sort parameter
        """
        from app.db.models import database_proxy

        repo = SqliteSummaryRepositoryAdapter(database_proxy)

        return await repo.async_get_user_summaries(
            user_id=user_id,
            limit=limit,
            offset=offset,
            is_read=is_read,
            is_favorited=is_favorited,
            lang=lang,
            start_date=start_date,
            end_date=end_date,
            sort=sort,
        )

    @staticmethod
    async def get_summary_by_id(user_id: int, summary_id: int) -> dict[str, Any]:
        """
        Get a single summary by ID with authorization check.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to retrieve

        Returns:
            Summary dictionary

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        from app.db.models import database_proxy

        repo = SqliteSummaryRepositoryAdapter(database_proxy)

        summary = await repo.async_get_summary_by_id(summary_id)

        # Check authorization (repo returns request data joined)
        if not summary or summary.get("user_id") != user_id or summary.get("is_deleted"):
            raise ResourceNotFoundError("Summary", summary_id)

        return summary

    @staticmethod
    async def update_summary(
        user_id: int, summary_id: int, is_read: bool | None = None
    ) -> dict[str, Any]:
        """
        Update a summary's properties.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to update
            is_read: New read status (if provided)

        Returns:
            Updated Summary dictionary

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        from app.db.models import database_proxy

        repo = SqliteSummaryRepositoryAdapter(database_proxy)

        # Get with authorization check
        summary = await repo.async_get_summary_by_id(summary_id)
        if not summary or summary.get("user_id") != user_id or summary.get("is_deleted"):
            raise ResourceNotFoundError("Summary", summary_id)

        # Update fields
        if is_read is not None:
            if is_read:
                await repo.async_mark_summary_as_read(summary_id)
            else:
                await repo.async_mark_summary_as_unread(summary_id)

        logger.info(
            f"Summary {summary_id} updated by user {user_id}",
            extra={"summary_id": summary_id, "user_id": user_id, "is_read": is_read},
        )

        return await repo.async_get_summary_by_id(summary_id)

    @staticmethod
    async def delete_summary(user_id: int, summary_id: int) -> None:
        """
        Delete (soft delete) a summary.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to delete

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        from app.db.models import database_proxy

        repo = SqliteSummaryRepositoryAdapter(database_proxy)

        # Get with authorization check
        summary = await repo.async_get_summary_by_id(summary_id)
        if not summary or summary.get("user_id") != user_id or summary.get("is_deleted"):
            raise ResourceNotFoundError("Summary", summary_id)

        await repo.async_soft_delete_summary(summary_id)

        logger.info(
            f"Summary {summary_id} soft-deleted by user {user_id}",
            extra={"summary_id": summary_id, "user_id": user_id},
        )

    @staticmethod
    async def toggle_favorite(user_id: int, summary_id: int) -> bool:
        """
        Toggle favorite status of a summary.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to toggle

        Returns:
            New is_favorited status

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        from app.db.models import database_proxy

        repo = SqliteSummaryRepositoryAdapter(database_proxy)

        # Get with authorization check
        summary = await repo.async_get_summary_by_id(summary_id)
        if not summary or summary.get("user_id") != user_id or summary.get("is_deleted"):
            raise ResourceNotFoundError("Summary", summary_id)

        new_status = await repo.async_toggle_favorite(summary_id)

        logger.info(
            f"Summary {summary_id} favorite status toggled to {new_status} by user {user_id}",
            extra={
                "summary_id": summary_id,
                "user_id": user_id,
                "is_favorited": new_status,
            },
        )

        return new_status
