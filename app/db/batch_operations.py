"""Batch database operations for bulk inserts and updates.

Provides efficient bulk operations with transaction management.
"""

from __future__ import annotations

import logging
from typing import Any

import peewee

from app.db.models import LLMCall, Request, Summary

logger = logging.getLogger(__name__)


class BatchOperations:
    """Provides batch insert/update operations for database efficiency."""

    def __init__(self, database: peewee.Database):
        """Initialize batch operations.

        Args:
            database: Peewee database instance
        """
        self.database = database

    def insert_llm_calls_batch(
        self,
        calls: list[dict[str, Any]],
    ) -> list[int]:
        """Insert multiple LLM calls in a single transaction.

        Args:
            calls: List of LLM call data dictionaries

        Returns:
            List of inserted LLM call IDs

        Example:
            >>> calls = [
            ...     {
            ...         "request_id": 1,
            ...         "provider": "openrouter",
            ...         "model": "gpt-4",
            ...         "status": "ok"
            ...     },
            ...     ...
            ... ]
            >>> ids = batch.insert_llm_calls_batch(calls)
        """
        if not calls:
            return []

        call_ids = []
        with self.database.atomic():
            for call_data in calls:
                # Prepare JSON payloads
                request_id = call_data.get("request_id")
                provider = call_data.get("provider")
                model = call_data.get("model")
                endpoint = call_data.get("endpoint")
                status = call_data.get("status")
                error_text = call_data.get("error_text")
                tokens_prompt = call_data.get("tokens_prompt")
                tokens_completion = call_data.get("tokens_completion")
                cost_usd = call_data.get("cost_usd")
                latency_ms = call_data.get("latency_ms")

                # Create LLM call
                call = LLMCall.create(
                    request=request_id,
                    provider=provider,
                    model=model,
                    endpoint=endpoint,
                    status=status,
                    error_text=error_text,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                )
                call_ids.append(call.id)

        logger.info(
            "llm_calls_batch_inserted",
            extra={"count": len(call_ids)},
        )
        return call_ids

    def update_request_statuses_batch(
        self,
        updates: list[tuple[int, str]],
    ) -> int:
        """Update multiple request statuses in a single transaction.

        Args:
            updates: List of (request_id, status) tuples

        Returns:
            Number of rows updated

        Example:
            >>> updates = [(1, "ok"), (2, "error"), (3, "ok")]
            >>> count = batch.update_request_statuses_batch(updates)
        """
        if not updates:
            return 0

        updated = 0
        with self.database.atomic():
            for request_id, status in updates:
                rows = (
                    Request.update({Request.status: status})
                    .where(Request.id == request_id)
                    .execute()
                )
                updated += rows

        logger.info(
            "request_statuses_batch_updated",
            extra={"count": updated},
        )
        return updated

    def mark_summaries_as_read_batch(
        self,
        summary_ids: list[int],
    ) -> int:
        """Mark multiple summaries as read in a single query.

        Args:
            summary_ids: List of summary IDs to mark as read

        Returns:
            Number of rows updated

        Example:
            >>> summary_ids = [1, 2, 3, 4, 5]
            >>> count = batch.mark_summaries_as_read_batch(summary_ids)
        """
        if not summary_ids:
            return 0

        rows = Summary.update({Summary.is_read: True}).where(Summary.id.in_(summary_ids)).execute()

        logger.info(
            "summaries_batch_marked_read",
            extra={"count": rows},
        )
        return rows

    def delete_requests_batch(
        self,
        request_ids: list[int],
    ) -> int:
        """Delete multiple requests (CASCADE will handle related records).

        Args:
            request_ids: List of request IDs to delete

        Returns:
            Number of rows deleted

        Example:
            >>> request_ids = [1, 2, 3]
            >>> count = batch.delete_requests_batch(request_ids)
        """
        if not request_ids:
            return 0

        with self.database.atomic():
            rows = Request.delete().where(Request.id.in_(request_ids)).execute()

        logger.info(
            "requests_batch_deleted",
            extra={"count": rows},
        )
        return rows

    def get_requests_by_ids_batch(
        self,
        request_ids: list[int],
    ) -> list[Request]:
        """Fetch multiple requests by ID in a single query.

        Args:
            request_ids: List of request IDs to fetch

        Returns:
            List of Request model instances

        Example:
            >>> request_ids = [1, 2, 3]
            >>> requests = batch.get_requests_by_ids_batch(request_ids)
        """
        if not request_ids:
            return []

        requests = list(Request.select().where(Request.id.in_(request_ids)).order_by(Request.id))

        logger.debug(
            "requests_batch_fetched",
            extra={"count": len(requests)},
        )
        return requests

    def get_summaries_by_request_ids_batch(
        self,
        request_ids: list[int],
    ) -> list[Summary]:
        """Fetch multiple summaries by request ID in a single query.

        Args:
            request_ids: List of request IDs

        Returns:
            List of Summary model instances

        Example:
            >>> request_ids = [1, 2, 3]
            >>> summaries = batch.get_summaries_by_request_ids_batch(request_ids)
        """
        if not request_ids:
            return []

        summaries = list(
            Summary.select().where(Summary.request.in_(request_ids)).order_by(Summary.request)
        )

        logger.debug(
            "summaries_batch_fetched",
            extra={"count": len(summaries)},
        )
        return summaries
