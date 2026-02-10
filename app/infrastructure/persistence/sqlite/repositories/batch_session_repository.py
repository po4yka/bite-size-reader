"""SQLite implementation of batch session repository.

This adapter handles CRUD operations for BatchSession and BatchSessionItem models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import BatchSession, BatchSessionItem, Request, Summary, model_to_dict
from app.db.utils import prepare_json_payload
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteBatchSessionRepositoryAdapter(SqliteBaseRepository):
    """Adapter for batch session persistence operations."""

    async def async_create_batch_session(
        self,
        user_id: int,
        correlation_id: str,
        total_urls: int,
    ) -> int:
        """Create a new batch session.

        Args:
            user_id: Telegram user ID
            correlation_id: Unique correlation ID for the batch
            total_urls: Total number of URLs in the batch

        Returns:
            The created batch session ID
        """

        def _create() -> int:
            session = BatchSession.create(
                user=user_id,
                correlation_id=correlation_id,
                total_urls=total_urls,
                status="processing",
            )
            return session.id

        return await self._execute(_create, operation_name="create_batch_session")

    async def async_get_batch_session(self, session_id: int) -> dict[str, Any] | None:
        """Get a batch session by ID.

        Args:
            session_id: Batch session ID

        Returns:
            Batch session dict or None if not found
        """

        def _get() -> dict[str, Any] | None:
            session = BatchSession.get_or_none(BatchSession.id == session_id)
            return model_to_dict(session)

        return await self._execute(_get, operation_name="get_batch_session", read_only=True)

    async def async_get_batch_session_by_correlation_id(
        self, correlation_id: str
    ) -> dict[str, Any] | None:
        """Get a batch session by correlation ID.

        Args:
            correlation_id: Batch correlation ID

        Returns:
            Batch session dict or None if not found
        """

        def _get() -> dict[str, Any] | None:
            session = BatchSession.get_or_none(BatchSession.correlation_id == correlation_id)
            return model_to_dict(session)

        return await self._execute(
            _get, operation_name="get_batch_session_by_correlation_id", read_only=True
        )

    async def async_update_batch_session_counts(
        self,
        session_id: int,
        successful_count: int,
        failed_count: int,
    ) -> None:
        """Update batch session processing counts.

        Args:
            session_id: Batch session ID
            successful_count: Number of successfully processed URLs
            failed_count: Number of failed URLs
        """

        def _update() -> None:
            BatchSession.update(
                {
                    BatchSession.successful_count: successful_count,
                    BatchSession.failed_count: failed_count,
                    BatchSession.updated_at: datetime.now(UTC),
                }
            ).where(BatchSession.id == session_id).execute()

        await self._execute(_update, operation_name="update_batch_session_counts")

    async def async_update_batch_session_status(
        self,
        session_id: int,
        status: str,
        analysis_status: str | None = None,
        processing_time_ms: int | None = None,
    ) -> None:
        """Update batch session status.

        Args:
            session_id: Batch session ID
            status: New status (processing, completed, error)
            analysis_status: Optional analysis status (pending, analyzing, complete, skipped, error)
            processing_time_ms: Optional total processing time
        """

        def _update() -> None:
            update_fields: dict[Any, Any] = {
                BatchSession.status: status,
                BatchSession.updated_at: datetime.now(UTC),
            }
            if analysis_status is not None:
                update_fields[BatchSession.analysis_status] = analysis_status
            if processing_time_ms is not None:
                update_fields[BatchSession.processing_time_ms] = processing_time_ms

            BatchSession.update(update_fields).where(BatchSession.id == session_id).execute()

        await self._execute(_update, operation_name="update_batch_session_status")

    async def async_update_batch_session_relationship(
        self,
        session_id: int,
        relationship_type: str,
        relationship_confidence: float,
        relationship_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update batch session relationship analysis results.

        Args:
            session_id: Batch session ID
            relationship_type: Detected relationship type
            relationship_confidence: Confidence score (0.0-1.0)
            relationship_metadata: Optional additional metadata
        """

        def _update() -> None:
            update_fields: dict[Any, Any] = {
                BatchSession.relationship_type: relationship_type,
                BatchSession.relationship_confidence: relationship_confidence,
                BatchSession.analysis_status: "complete",
                BatchSession.updated_at: datetime.now(UTC),
            }
            if relationship_metadata is not None:
                update_fields[BatchSession.relationship_metadata_json] = prepare_json_payload(
                    relationship_metadata
                )

            BatchSession.update(update_fields).where(BatchSession.id == session_id).execute()

        await self._execute(_update, operation_name="update_batch_session_relationship")

    async def async_update_batch_session_combined_summary(
        self,
        session_id: int,
        combined_summary: dict[str, Any],
    ) -> None:
        """Update batch session with combined summary.

        Args:
            session_id: Batch session ID
            combined_summary: Combined summary JSON
        """

        def _update() -> None:
            BatchSession.update(
                {
                    BatchSession.combined_summary_json: prepare_json_payload(combined_summary),
                    BatchSession.updated_at: datetime.now(UTC),
                }
            ).where(BatchSession.id == session_id).execute()

        await self._execute(_update, operation_name="update_batch_session_combined_summary")

    async def async_add_batch_session_item(
        self,
        session_id: int,
        request_id: int,
        position: int,
        is_series_part: bool = False,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> int:
        """Add an item to a batch session.

        Args:
            session_id: Batch session ID
            request_id: Request ID for the item
            position: Position in batch (0-indexed)
            is_series_part: Whether this is part of a series
            series_order: Order in series (if applicable)
            series_title: Series title (if applicable)

        Returns:
            Created item ID
        """

        def _create() -> int:
            item = BatchSessionItem.create(
                batch_session=session_id,
                request=request_id,
                position=position,
                is_series_part=is_series_part,
                series_order=series_order,
                series_title=series_title,
            )
            return item.id

        return await self._execute(_create, operation_name="add_batch_session_item")

    async def async_get_batch_session_items(
        self, session_id: int
    ) -> list[dict[str, Any]]:
        """Get all items for a batch session.

        Args:
            session_id: Batch session ID

        Returns:
            List of item dicts ordered by position
        """

        def _get() -> list[dict[str, Any]]:
            items = (
                BatchSessionItem.select()
                .where(BatchSessionItem.batch_session == session_id)
                .order_by(BatchSessionItem.position)
            )
            return [model_to_dict(item) or {} for item in items]

        return await self._execute(_get, operation_name="get_batch_session_items", read_only=True)

    async def async_get_batch_session_with_summaries(
        self, session_id: int
    ) -> dict[str, Any] | None:
        """Get a batch session with all its items and their summaries.

        Args:
            session_id: Batch session ID

        Returns:
            Dict containing session, items, and summaries, or None if not found
        """

        def _get() -> dict[str, Any] | None:
            session = BatchSession.get_or_none(BatchSession.id == session_id)
            if not session:
                return None

            session_dict = model_to_dict(session) or {}

            # Get items with their requests and summaries
            items_with_summaries = []
            items = (
                BatchSessionItem.select(BatchSessionItem, Request, Summary)
                .join(Request)
                .switch(BatchSessionItem)
                .join(Summary, peewee.JOIN.LEFT_OUTER, on=(Summary.request == BatchSessionItem.request))
                .where(BatchSessionItem.batch_session == session_id)
                .order_by(BatchSessionItem.position)
            )

            for item in items:
                item_dict = model_to_dict(item) or {}
                item_dict["request"] = model_to_dict(item.request) if item.request else None

                # Handle summary - it may be None or a model
                if hasattr(item, "request") and item.request:
                    try:
                        summary = Summary.get_or_none(Summary.request == item.request.id)
                        item_dict["summary"] = model_to_dict(summary) if summary else None
                    except Exception:
                        item_dict["summary"] = None
                else:
                    item_dict["summary"] = None

                items_with_summaries.append(item_dict)

            session_dict["items"] = items_with_summaries
            return session_dict

        return await self._execute(
            _get, operation_name="get_batch_session_with_summaries", read_only=True
        )

    async def async_update_batch_session_item_series_info(
        self,
        item_id: int,
        is_series_part: bool,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> None:
        """Update series information for a batch session item.

        Args:
            item_id: Item ID
            is_series_part: Whether this is part of a series
            series_order: Order in series
            series_title: Series title
        """

        def _update() -> None:
            BatchSessionItem.update(
                {
                    BatchSessionItem.is_series_part: is_series_part,
                    BatchSessionItem.series_order: series_order,
                    BatchSessionItem.series_title: series_title,
                }
            ).where(BatchSessionItem.id == item_id).execute()

        await self._execute(_update, operation_name="update_batch_session_item_series_info")

    async def async_get_user_batch_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get batch sessions for a user.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of sessions to return
            offset: Offset for pagination
            status: Optional status filter

        Returns:
            List of batch session dicts
        """

        def _get() -> list[dict[str, Any]]:
            query = (
                BatchSession.select()
                .where(BatchSession.user == user_id)
                .order_by(BatchSession.created_at.desc())
            )

            if status:
                query = query.where(BatchSession.status == status)

            sessions = query.limit(limit).offset(offset)
            return [model_to_dict(s) or {} for s in sessions]

        return await self._execute(_get, operation_name="get_user_batch_sessions", read_only=True)

    async def async_delete_batch_session(self, session_id: int) -> bool:
        """Delete a batch session and all its items.

        Args:
            session_id: Batch session ID

        Returns:
            True if deleted, False if not found
        """

        def _delete() -> bool:
            # Items are deleted via CASCADE
            deleted = BatchSession.delete().where(BatchSession.id == session_id).execute()
            return deleted > 0

        return await self._execute(_delete, operation_name="delete_batch_session")
