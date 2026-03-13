"""Summary service - business logic for summary operations."""

from typing import Any

from app.api.dependencies.database import resolve_repository_session
from app.api.exceptions import ResourceNotFoundError
from app.application.use_cases.summary_read_model import SummaryReadModelUseCase
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = get_logger(__name__)


class SummaryService:
    """Service for summary-related business logic."""

    @staticmethod
    def _build_use_case() -> SummaryReadModelUseCase:
        session = resolve_repository_session()
        return SummaryReadModelUseCase(
            summary_repository=SqliteSummaryRepositoryAdapter(session),
            request_repository=SqliteRequestRepositoryAdapter(session),
            crawl_result_repository=SqliteCrawlResultRepositoryAdapter(session),
            llm_repository=SqliteLLMRepositoryAdapter(session),
        )

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
        use_case = SummaryService._build_use_case()
        return await use_case.get_user_summaries(
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
        use_case = SummaryService._build_use_case()
        summary = await use_case.get_summary_by_id_for_user(user_id=user_id, summary_id=summary_id)
        if not summary:
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
        use_case = SummaryService._build_use_case()
        updated_summary = await use_case.update_summary(
            user_id=user_id,
            summary_id=summary_id,
            is_read=is_read,
        )
        if not updated_summary:
            raise ResourceNotFoundError("Summary", summary_id)

        logger.info(
            f"Summary {summary_id} updated by user {user_id}",
            extra={"summary_id": summary_id, "user_id": user_id, "is_read": is_read},
        )

        return updated_summary

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
        use_case = SummaryService._build_use_case()
        deleted = await use_case.soft_delete_summary(user_id=user_id, summary_id=summary_id)
        if not deleted:
            raise ResourceNotFoundError("Summary", summary_id)

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
        use_case = SummaryService._build_use_case()
        new_status = await use_case.toggle_favorite(user_id=user_id, summary_id=summary_id)
        if new_status is None:
            raise ResourceNotFoundError("Summary", summary_id)

        logger.info(
            f"Summary {summary_id} favorite status toggled to {new_status} by user {user_id}",
            extra={
                "summary_id": summary_id,
                "user_id": user_id,
                "is_favorited": new_status,
            },
        )

        return new_status
