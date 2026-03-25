"""Read operations for the SQLite request repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import peewee

from app.db.models import CrawlResult, Request, Summary, model_to_dict

from ._joined_row_utils import aliased_model_fields, extract_aliased_model
from ._repository_mixin_base import SqliteRepositoryMixinBase

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


class RequestRepositoryReadMixin(SqliteRepositoryMixinBase):
    """Read/query request operations."""

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Get a request by its ID."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(Request.id == request_id)
            return model_to_dict(request)

        return await self._execute(_get, operation_name="get_request_by_id", read_only=True)

    async def async_get_request_context(self, request_id: int) -> dict[str, Any] | None:
        """Get a request with its one-to-one related records in a single read."""

        def _get() -> dict[str, Any] | None:
            row: Mapping[str, Any] | None = (
                Request.select(
                    *aliased_model_fields(Request, "request"),
                    *aliased_model_fields(CrawlResult, "crawl_result"),
                    *aliased_model_fields(Summary, "summary"),
                )
                .join(
                    CrawlResult,
                    peewee.JOIN.LEFT_OUTER,
                    on=(CrawlResult.request == Request.id),
                )
                .switch(Request)
                .join(
                    Summary,
                    peewee.JOIN.LEFT_OUTER,
                    on=(Summary.request == Request.id),
                )
                .where(Request.id == request_id)
                .dicts()
                .first()
            )
            if row is None:
                return None

            request_data = extract_aliased_model(row, Request, "request")
            if request_data is None:
                return None

            return {
                "request": request_data,
                "crawl_result": extract_aliased_model(row, CrawlResult, "crawl_result"),
                "summary": extract_aliased_model(row, Summary, "summary"),
            }

        return await self._execute(_get, operation_name="get_request_context", read_only=True)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Get a request by its deduplication hash."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
            return model_to_dict(request)

        return await self._execute(
            _get, operation_name="get_request_by_dedupe_hash", read_only=True
        )

    async def async_get_latest_request_by_correlation_id(
        self, correlation_id: str
    ) -> dict[str, Any] | None:
        """Get the latest request by correlation ID."""

        def _get() -> dict[str, Any] | None:
            request = (
                Request.select()
                .where(Request.correlation_id == correlation_id)
                .order_by(Request.created_at.desc())
                .first()
            )
            return model_to_dict(request)

        return await self._execute(
            _get,
            operation_name="get_latest_request_by_correlation_id",
            read_only=True,
        )

    async def async_get_requests_by_ids(
        self, request_ids: list[int], user_id: int | None = None
    ) -> dict[int, dict[str, Any]]:
        """Get multiple requests by IDs, optionally filtered by user."""

        def _get() -> dict[int, dict[str, Any]]:
            if not request_ids:
                return {}
            query = Request.select().where(Request.id.in_(request_ids))
            if user_id is not None:
                query = query.where(Request.user_id == user_id)
            return {req.id: model_to_dict(req) or {} for req in query}

        return await self._execute(_get, operation_name="get_requests_by_ids", read_only=True)

    async def async_get_request_by_forward(
        self, chat_id: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Get a request by forwarded message details."""

        def _get() -> dict[str, Any] | None:
            request = Request.get_or_none(
                (Request.fwd_from_chat_id == chat_id) & (Request.fwd_from_msg_id == fwd_message_id)
            )
            return model_to_dict(request)

        return await self._execute(_get, operation_name="get_request_by_forward", read_only=True)

    async def async_get_request_error_context(self, request_id: int) -> dict[str, Any] | None:
        """Get structured request error context snapshot."""

        def _get() -> dict[str, Any] | None:
            row = Request.select(Request.error_context_json).where(Request.id == request_id).first()
            if not row:
                return None
            value = row.error_context_json
            return value if isinstance(value, dict) else None

        return await self._execute(_get, operation_name="get_request_error_context", read_only=True)

    async def async_count_pending_requests_before(self, created_at: datetime) -> int:
        """Count pending requests created before *created_at*."""

        def _count() -> int:
            return (
                Request.select()
                .where((Request.status == "pending") & (Request.created_at < created_at))
                .count()
            )

        return await self._execute(
            _count,
            operation_name="count_pending_requests_before",
            read_only=True,
        )

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version across requests owned by *user_id*."""

        def _query() -> int | None:
            return (
                Request.select(peewee.fn.MAX(Request.server_version))
                .where(Request.user_id == user_id)
                .scalar()
            )

        return await self._execute(
            _query, operation_name="get_max_server_version_request", read_only=True
        )

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all requests for a user for sync operations."""

        def _get() -> list[dict[str, Any]]:
            requests = Request.select().where(Request.user_id == user_id)
            return [model_to_dict(req) or {} for req in requests]

        return await self._execute(_get, operation_name="get_all_requests_for_user", read_only=True)

    async def async_get_request_id_by_url_with_summary(self, user_id: int, url: str) -> int | None:
        """Get a request ID by URL when the request already has a summary."""

        def _get() -> int | None:
            request = (
                Request.select(Request.id)
                .join(Summary)
                .where(
                    (Request.user_id == user_id)
                    & ((Request.input_url == url) | (Request.normalized_url == url))
                    & (Summary.request == Request.id)
                )
                .order_by(Request.created_at.desc())
                .first()
            )
            return request.id if request else None

        return await self._execute(
            _get, operation_name="get_request_id_by_url_with_summary", read_only=True
        )
