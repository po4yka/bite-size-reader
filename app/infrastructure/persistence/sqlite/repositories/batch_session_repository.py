"""SQLAlchemy implementation of batch session repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update

from app.core.time_utils import UTC
from app.db.json_utils import prepare_json_payload
from app.db.models import BatchSession, BatchSessionItem, Request, Summary, model_to_dict

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteBatchSessionRepositoryAdapter:
    """Adapter for batch session persistence operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_create_batch_session(
        self,
        user_id: int,
        correlation_id: str,
        total_urls: int,
    ) -> int:
        """Create a new batch session."""
        async with self._database.transaction() as db_session:
            session = BatchSession(
                user_id=user_id,
                correlation_id=correlation_id,
                total_urls=total_urls,
                status="processing",
            )
            db_session.add(session)
            await db_session.flush()
            return session.id

    async def async_get_batch_session(self, session_id: int) -> dict[str, Any] | None:
        """Get a batch session by ID."""
        async with self._database.session() as db_session:
            session = await db_session.get(BatchSession, session_id)
            return _session_to_dict(session)

    async def async_get_batch_session_by_correlation_id(
        self, correlation_id: str
    ) -> dict[str, Any] | None:
        """Get a batch session by correlation ID."""
        async with self._database.session() as db_session:
            session = await db_session.scalar(
                select(BatchSession).where(BatchSession.correlation_id == correlation_id)
            )
            return _session_to_dict(session)

    async def async_update_batch_session_counts(
        self,
        session_id: int,
        successful_count: int,
        failed_count: int,
    ) -> None:
        """Update batch session processing counts."""
        async with self._database.transaction() as db_session:
            await db_session.execute(
                update(BatchSession)
                .where(BatchSession.id == session_id)
                .values(
                    successful_count=successful_count,
                    failed_count=failed_count,
                    updated_at=datetime.now(UTC),
                )
            )

    async def async_update_batch_session_status(
        self,
        session_id: int,
        status: str,
        analysis_status: str | None = None,
        processing_time_ms: int | None = None,
    ) -> None:
        """Update batch session status."""
        update_fields: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        if analysis_status is not None:
            update_fields["analysis_status"] = analysis_status
        if processing_time_ms is not None:
            update_fields["processing_time_ms"] = processing_time_ms

        async with self._database.transaction() as db_session:
            await db_session.execute(
                update(BatchSession).where(BatchSession.id == session_id).values(**update_fields)
            )

    async def async_update_batch_session_relationship(
        self,
        session_id: int,
        relationship_type: str,
        relationship_confidence: float,
        relationship_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update batch session relationship analysis results."""
        update_fields: dict[str, Any] = {
            "relationship_type": relationship_type,
            "relationship_confidence": relationship_confidence,
            "analysis_status": "complete",
            "updated_at": datetime.now(UTC),
        }
        if relationship_metadata is not None:
            update_fields["relationship_metadata_json"] = prepare_json_payload(
                relationship_metadata
            )

        async with self._database.transaction() as db_session:
            await db_session.execute(
                update(BatchSession).where(BatchSession.id == session_id).values(**update_fields)
            )

    async def async_update_batch_session_combined_summary(
        self,
        session_id: int,
        combined_summary: dict[str, Any],
    ) -> None:
        """Update batch session with combined summary."""
        async with self._database.transaction() as db_session:
            await db_session.execute(
                update(BatchSession)
                .where(BatchSession.id == session_id)
                .values(
                    combined_summary_json=prepare_json_payload(combined_summary),
                    updated_at=datetime.now(UTC),
                )
            )

    async def async_add_batch_session_item(
        self,
        session_id: int,
        request_id: int,
        position: int,
        is_series_part: bool = False,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> int:
        """Add an item to a batch session."""
        async with self._database.transaction() as db_session:
            item = BatchSessionItem(
                batch_session_id=session_id,
                request_id=request_id,
                position=position,
                is_series_part=is_series_part,
                series_order=series_order,
                series_title=series_title,
            )
            db_session.add(item)
            await db_session.flush()
            return item.id

    async def async_get_batch_session_items(self, session_id: int) -> list[dict[str, Any]]:
        """Get all items for a batch session."""
        async with self._database.session() as db_session:
            items = (
                await db_session.execute(
                    select(BatchSessionItem)
                    .where(BatchSessionItem.batch_session_id == session_id)
                    .order_by(BatchSessionItem.position)
                )
            ).scalars()
            return [_item_to_dict(item) or {} for item in items]

    async def async_get_batch_session_with_summaries(
        self, session_id: int
    ) -> dict[str, Any] | None:
        """Get a batch session with all its items and their summaries."""
        async with self._database.session() as db_session:
            session = await db_session.get(BatchSession, session_id)
            if session is None:
                return None

            session_dict = _session_to_dict(session) or {}
            rows = await db_session.execute(
                select(BatchSessionItem, Request, Summary)
                .join(Request, BatchSessionItem.request_id == Request.id)
                .outerjoin(Summary, Summary.request_id == BatchSessionItem.request_id)
                .where(BatchSessionItem.batch_session_id == session_id)
                .order_by(BatchSessionItem.position)
            )
            items_with_summaries: list[dict[str, Any]] = []
            for item, request, summary in rows:
                item_dict = _item_to_dict(item) or {}
                item_dict["request"] = model_to_dict(request)
                item_dict["summary"] = model_to_dict(summary)
                items_with_summaries.append(item_dict)

            session_dict["items"] = items_with_summaries
            return session_dict

    async def async_update_batch_session_item_series_info(
        self,
        item_id: int,
        is_series_part: bool,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> None:
        """Update series information for a batch session item."""
        async with self._database.transaction() as db_session:
            await db_session.execute(
                update(BatchSessionItem)
                .where(BatchSessionItem.id == item_id)
                .values(
                    is_series_part=is_series_part,
                    series_order=series_order,
                    series_title=series_title,
                )
            )

    async def async_get_user_batch_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get batch sessions for a user."""
        async with self._database.session() as db_session:
            stmt = (
                select(BatchSession)
                .where(BatchSession.user_id == user_id)
                .order_by(BatchSession.created_at.desc())
            )
            if status:
                stmt = stmt.where(BatchSession.status == status)
            sessions = (await db_session.execute(stmt.limit(limit).offset(offset))).scalars()
            return [_session_to_dict(session) or {} for session in sessions]

    async def async_delete_batch_session(self, session_id: int) -> bool:
        """Delete a batch session and all its items."""
        async with self._database.transaction() as db_session:
            result = await db_session.execute(
                delete(BatchSession).where(BatchSession.id == session_id).returning(BatchSession.id)
            )
            return result.scalar_one_or_none() is not None


def _session_to_dict(session: BatchSession | None) -> dict[str, Any] | None:
    data = model_to_dict(session)
    if data is not None:
        data["user"] = data.get("user_id")
    return data


def _item_to_dict(item: BatchSessionItem | None) -> dict[str, Any] | None:
    data = model_to_dict(item)
    if data is not None:
        data["batch_session"] = data.get("batch_session_id")
        data["request"] = data.get("request_id")
    return data
