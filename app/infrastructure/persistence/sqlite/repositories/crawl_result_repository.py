"""SQLite implementation of crawl result repository.

This adapter translates between crawl result data and database records.
"""

from __future__ import annotations

from typing import Any

import peewee

from app.db.models import CrawlResult, model_to_dict
from app.db.utils import prepare_json_payload
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteCrawlResultRepositoryAdapter(SqliteBaseRepository):
    """Adapter that implements CrawlResultRepository using Peewee models directly.

    This replaces the legacy delegation to the monolithic Database class.
    """

    async def async_insert_crawl_result(
        self,
        request_id: int,
        success: bool,
        markdown: str | None = None,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> int:
        """Insert a crawl result."""

        def _insert() -> int:
            try:
                # We map the simplified protocol arguments to the database model
                # Note: Many fields present in database.py are not in the protocol signature
                # We default them or extract from metadata if needed
                result = CrawlResult.create(
                    request=request_id,
                    firecrawl_success=success,
                    content_markdown=markdown,
                    error_text=error,
                    metadata_json=prepare_json_payload(metadata_json, default={}),
                    # Set defaults for fields required by schema but missing from protocol
                    # (Assuming Peewee model handles defaults or nullable fields correctly)
                )
                return result.id
            except peewee.IntegrityError:
                # Idempotency: return existing result ID if conflict on request_id (unique)
                existing = CrawlResult.get_or_none(CrawlResult.request == request_id)
                if existing:
                    return existing.id
                raise

        return await self._execute(_insert, operation_name="insert_crawl_result")

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get a crawl result by request ID."""

        def _get() -> dict[str, Any] | None:
            result = CrawlResult.get_or_none(CrawlResult.request == request_id)
            return model_to_dict(result)

        return await self._execute(
            _get, operation_name="get_crawl_result_by_request", read_only=True
        )

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all crawl results for a user (for sync operations).

        Returns:
            List of crawl result dicts with request_id flattened.
        """
        from peewee import JOIN

        from app.db.models import Request

        def _get() -> list[dict[str, Any]]:
            crawl_results = (
                CrawlResult.select(CrawlResult, Request)
                .join(Request, JOIN.INNER)
                .where(Request.user_id == user_id)
            )
            result = []
            for cr in crawl_results:
                c_dict = model_to_dict(cr) or {}
                # Flatten request to just the ID for sync
                if "request" in c_dict and isinstance(c_dict["request"], dict):
                    c_dict["request"] = c_dict["request"]["id"]
                result.append(c_dict)
            return result

        return await self._execute(
            _get, operation_name="get_all_crawl_results_for_user", read_only=True
        )
