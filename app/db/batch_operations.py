"""Batch database operations for bulk inserts and updates."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, insert, select, update

from app.core.logging_utils import get_logger
from app.db.models import LLMCall, Request, Summary

if TYPE_CHECKING:
    from app.db.session import Database

logger = get_logger(__name__)


class BatchOperations:
    """Provides batch operations backed by SQLAlchemy async sessions."""

    def __init__(self, database: Database):
        self.database = database

    async def async_insert_llm_calls_batch(self, calls: list[dict[str, Any]]) -> list[int]:
        """Insert multiple LLM calls in a single transaction."""
        if not calls:
            return []

        values = [_normalize_llm_call(call) for call in calls]
        async with self.database.transaction() as session:
            rows = await session.execute(insert(LLMCall).returning(LLMCall.id), values)
            call_ids = [int(row_id) for row_id in rows.scalars().all()]

        logger.info("llm_calls_batch_inserted", extra={"count": len(call_ids)})
        return call_ids

    async def async_update_request_statuses_batch(self, updates: list[tuple[int, str]]) -> int:
        """Update multiple request statuses in a single transaction."""
        if not updates:
            return 0

        updated = 0
        async with self.database.transaction() as session:
            for request_id, status in updates:
                result = await session.execute(
                    update(Request).where(Request.id == request_id).values(status=status)
                )
                updated += int(result.rowcount or 0)

        logger.info("request_statuses_batch_updated", extra={"count": updated})
        return updated

    async def async_mark_summaries_as_read_batch(self, summary_ids: list[int]) -> int:
        """Mark multiple summaries as read in a single query."""
        if not summary_ids:
            return 0

        async with self.database.transaction() as session:
            result = await session.execute(
                update(Summary).where(Summary.id.in_(summary_ids)).values(is_read=True)
            )
            rows = int(result.rowcount or 0)

        logger.info("summaries_batch_marked_read", extra={"count": rows})
        return rows

    async def async_delete_requests_batch(self, request_ids: list[int]) -> int:
        """Delete multiple requests; database cascades handle related records."""
        if not request_ids:
            return 0

        async with self.database.transaction() as session:
            result = await session.execute(delete(Request).where(Request.id.in_(request_ids)))
            rows = int(result.rowcount or 0)

        logger.info("requests_batch_deleted", extra={"count": rows})
        return rows

    async def async_get_requests_by_ids_batch(self, request_ids: list[int]) -> list[Request]:
        """Fetch multiple requests by ID in a single query."""
        if not request_ids:
            return []

        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(Request).where(Request.id.in_(request_ids)).order_by(Request.id)
                )
            ).scalars().all()

        logger.debug("requests_batch_fetched", extra={"count": len(rows)})
        return list(rows)

    async def async_get_summaries_by_request_ids_batch(
        self, request_ids: list[int]
    ) -> list[Summary]:
        """Fetch multiple summaries by request ID in a single query."""
        if not request_ids:
            return []

        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(Summary)
                    .where(Summary.request_id.in_(request_ids))
                    .order_by(Summary.request_id)
                )
            ).scalars().all()

        logger.debug("summaries_batch_fetched", extra={"count": len(rows)})
        return list(rows)

    def insert_llm_calls_batch(self, calls: list[dict[str, Any]]) -> list[int]:
        """Synchronous compatibility wrapper for async_insert_llm_calls_batch."""
        return asyncio.run(self.async_insert_llm_calls_batch(calls))

    def update_request_statuses_batch(self, updates: list[tuple[int, str]]) -> int:
        """Synchronous compatibility wrapper for async_update_request_statuses_batch."""
        return asyncio.run(self.async_update_request_statuses_batch(updates))

    def mark_summaries_as_read_batch(self, summary_ids: list[int]) -> int:
        """Synchronous compatibility wrapper for async_mark_summaries_as_read_batch."""
        return asyncio.run(self.async_mark_summaries_as_read_batch(summary_ids))

    def delete_requests_batch(self, request_ids: list[int]) -> int:
        """Synchronous compatibility wrapper for async_delete_requests_batch."""
        return asyncio.run(self.async_delete_requests_batch(request_ids))

    def get_requests_by_ids_batch(self, request_ids: list[int]) -> list[Request]:
        """Synchronous compatibility wrapper for async_get_requests_by_ids_batch."""
        return asyncio.run(self.async_get_requests_by_ids_batch(request_ids))

    def get_summaries_by_request_ids_batch(self, request_ids: list[int]) -> list[Summary]:
        """Synchronous compatibility wrapper for async_get_summaries_by_request_ids_batch."""
        return asyncio.run(self.async_get_summaries_by_request_ids_batch(request_ids))


def _normalize_llm_call(call_data: dict[str, Any]) -> dict[str, Any]:
    allowed = set(LLMCall.__table__.columns.keys()) - {"id", "created_at", "updated_at"}
    values = {key: value for key, value in call_data.items() if key in allowed}
    if "request_id" not in values and "request" in call_data:
        values["request_id"] = call_data["request"]
    return values
