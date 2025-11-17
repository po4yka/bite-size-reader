"""SQLite implementation of summary repository.

This adapter translates between domain Summary models and database records.
"""

from datetime import datetime
from typing import Any

from app.core.time_utils import UTC
from app.domain.models.summary import Summary


class SqliteSummaryRepositoryAdapter:
    """Adapter that wraps the existing Database class for summary operations.

    This adapter implements the SummaryRepository protocol using the existing
    Database class, providing a bridge between the new domain layer and the
    existing infrastructure.
    """

    def __init__(self, database: Any) -> None:
        """Initialize the repository adapter.

        Args:
            database: The existing Database instance to wrap.

        """
        self._db = database

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary."""
        return await self._db.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=json_payload,
            insights_json=insights_json,
            is_read=is_read,
        )

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get the latest summary for a request."""
        return await self._db.async_get_summary_by_request(request_id)

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary by its ID."""
        return await self._db.async_get_summary_by_id(summary_id)

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get unread summaries for a user.

        Args:
            uid: User ID.
            cid: Chat ID.
            limit: Maximum number of summaries to return.
            topic: Optional topic filter for searching summaries.

        Returns:
            List of unread summary dictionaries.

        """
        return await self._db.async_get_unread_summaries(uid, cid, limit, topic)

    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get an unread summary by request ID."""
        return await self._db.async_get_unread_summary_by_request_id(request_id)

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark a summary as read."""
        await self._db.async_mark_summary_as_read(summary_id)

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Mark a summary as unread."""
        await self._db.async_mark_summary_as_unread(summary_id)

    async def async_update_summary_insights(
        self, summary_id: int, insights_json: dict[str, Any]
    ) -> None:
        """Update the insights field of a summary."""
        await self._db.async_update_summary_insights(summary_id, insights_json)

    def to_domain_model(self, db_summary: dict[str, Any]) -> Summary:
        """Convert database record to domain model.

        Args:
            db_summary: Dictionary from database query.

        Returns:
            Summary domain model.

        """

        return Summary(
            id=db_summary.get("id"),
            request_id=db_summary["request_id"],
            content=db_summary["json_payload"],
            language=db_summary["lang"],
            version=db_summary.get("version", 1),
            is_read=db_summary.get("is_read", False),
            insights=db_summary.get("insights_json"),
            created_at=db_summary.get("created_at", datetime.now(UTC)),
        )

    def from_domain_model(self, summary: Summary) -> dict[str, Any]:
        """Convert domain model to database record format.

        Args:
            summary: Summary domain model.

        Returns:
            Dictionary suitable for database operations.

        """
        result: dict[str, Any] = {
            "request_id": summary.request_id,
            "json_payload": summary.content,
            "lang": summary.language,
            "version": summary.version,
            "is_read": summary.is_read,
        }

        if summary.id is not None:
            result["id"] = summary.id

        if summary.insights is not None:
            result["insights_json"] = summary.insights

        return result
