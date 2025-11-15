"""Summary service - business logic for summary operations."""

from peewee import fn, Case

from app.db.models import Summary, Request as RequestModel
from app.api.exceptions import ResourceNotFoundError
from app.core.logging_utils import get_logger

logger = get_logger(__name__)


class SummaryService:
    """Service for summary-related business logic."""

    @staticmethod
    def get_user_summaries(
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        lang: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[Summary], int, int]:
        """
        Get paginated summaries for a user with filtering.

        Args:
            user_id: User ID for authorization
            limit: Maximum results to return
            offset: Results offset for pagination
            is_read: Filter by read status (None = all)
            lang: Filter by language
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            sort: Sort order (created_at_desc or created_at_asc)

        Returns:
            Tuple of (summaries list, total count, unread count)

        Raises:
            ValueError: If invalid sort parameter
        """
        # Build query with eager loading and user authorization
        query = (
            Summary.select(Summary, RequestModel)
            .join(RequestModel)
            .where(RequestModel.user_id == user_id)
        )

        # Apply filters
        if is_read is not None:
            query = query.where(Summary.is_read == is_read)

        if lang:
            query = query.where(Summary.lang == lang)

        if start_date:
            query = query.where(Summary.created_at >= start_date)

        if end_date:
            query = query.where(Summary.created_at <= end_date)

        # Apply sorting
        if sort == "created_at_desc":
            query = query.order_by(RequestModel.created_at.desc())
        elif sort == "created_at_asc":
            query = query.order_by(RequestModel.created_at.asc())
        else:
            raise ValueError(f"Invalid sort parameter: {sort}")

        # Get paginated results
        summaries = list(query.limit(limit).offset(offset))

        # Get stats with single aggregation query
        stats_query = (
            Summary.select(
                fn.COUNT(Summary.id).alias("total"),
                fn.SUM(Case(None, [(~Summary.is_read, 1)], 0)).alias("unread"),
            )
            .join(RequestModel)
            .where(RequestModel.user_id == user_id)
            .first()
        )

        total_summaries = stats_query.total if stats_query else 0
        unread_count = stats_query.unread if stats_query and stats_query.unread else 0

        return summaries, total_summaries, unread_count

    @staticmethod
    def get_summary_by_id(user_id: int, summary_id: int) -> Summary:
        """
        Get a single summary by ID with authorization check.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to retrieve

        Returns:
            Summary instance

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        summary = (
            Summary.select(Summary, RequestModel)
            .join(RequestModel)
            .where((Summary.id == summary_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not summary:
            raise ResourceNotFoundError("Summary", summary_id)

        return summary

    @staticmethod
    def update_summary(user_id: int, summary_id: int, is_read: bool | None = None) -> Summary:
        """
        Update a summary's properties.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to update
            is_read: New read status (if provided)

        Returns:
            Updated Summary instance

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        # Get with authorization check
        summary = (
            Summary.select()
            .join(RequestModel)
            .where((Summary.id == summary_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not summary:
            raise ResourceNotFoundError("Summary", summary_id)

        # Update fields
        if is_read is not None:
            summary.is_read = is_read

        summary.save()

        logger.info(
            f"Summary {summary_id} updated by user {user_id}",
            extra={"summary_id": summary_id, "user_id": user_id, "is_read": is_read},
        )

        return summary

    @staticmethod
    def delete_summary(user_id: int, summary_id: int) -> None:
        """
        Delete (soft delete) a summary.

        Args:
            user_id: User ID for authorization
            summary_id: Summary ID to delete

        Raises:
            ResourceNotFoundError: If summary not found or access denied
        """
        # Get with authorization check
        summary = (
            Summary.select()
            .join(RequestModel)
            .where((Summary.id == summary_id) & (RequestModel.user_id == user_id))
            .first()
        )

        if not summary:
            raise ResourceNotFoundError("Summary", summary_id)

        # Soft delete - mark as read
        summary.is_read = True
        summary.save()

        logger.info(
            f"Summary {summary_id} deleted by user {user_id}",
            extra={"summary_id": summary_id, "user_id": user_id},
        )
