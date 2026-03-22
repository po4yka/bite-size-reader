"""Read operations for the SQLite summary repository."""

from __future__ import annotations

from typing import Any

import peewee

from app.application.services.topic_search_utils import ensure_mapping
from app.db.models import CrawlResult, Request, Summary, model_to_dict

from ._joined_row_utils import aliased_model_fields, extract_aliased_model
from ._summary_repo_shared import SummaryRepositorySharedMixin


class SummaryRepositoryReadMixin(SummaryRepositorySharedMixin):
    """Read/query summary operations."""

    async def async_get_user_summaries(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        lang: str | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Get paginated summaries for a user with filtering and stats."""

        def _query() -> tuple[list[dict[str, Any]], int, int]:
            query = Summary.select(Summary, Request).join(Request).where(Request.user_id == user_id)

            if is_read is not None:
                query = query.where(Summary.is_read == is_read)
            if is_favorited is not None:
                query = query.where(Summary.is_favorited == is_favorited)

            query = query.where(~Summary.is_deleted)

            if lang:
                query = query.where(Summary.lang == lang)
            if start_date:
                query = query.where(Summary.created_at >= start_date)
            if end_date:
                query = query.where(Summary.created_at <= end_date)

            if sort == "created_at_desc":
                query = query.order_by(Request.created_at.desc())
            else:
                query = query.order_by(Request.created_at.asc())

            total_summaries = query.count()

            summaries_list = []
            for row in query.limit(limit).offset(offset):
                data = model_to_dict(row)
                if (
                    data is not None
                    and hasattr(row, "request")
                    and isinstance(row.request, Request)
                ):
                    data["request"] = model_to_dict(row.request)
                summaries_list.append(data)

            unread_count = (
                Summary.select()
                .join(Request)
                .where((Request.user_id == user_id) & (~Summary.is_read) & (~Summary.is_deleted))
                .count()
            )

            return summaries_list, total_summaries, unread_count

        return await self._execute(_query, operation_name="get_user_summaries", read_only=True)

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get the latest summary for a request."""

        def _get() -> dict[str, Any] | None:
            summary = Summary.get_or_none(Summary.request == request_id)
            return model_to_dict(summary)

        return await self._execute(_get, operation_name="get_summary_by_request", read_only=True)

    async def async_get_summary_id_by_request(self, request_id: int) -> int | None:
        """Get a summary ID by its request ID."""

        def _get() -> int | None:
            summary = Summary.select(Summary.id).where(Summary.request == request_id).first()
            return summary.id if summary else None

        return await self._execute(_get, operation_name="get_summary_id_by_request", read_only=True)

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary by its ID."""

        def _get() -> dict[str, Any] | None:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(Summary.id == summary_id)
                .first()
            )
            if not summary:
                return None

            data = model_to_dict(summary) or {}
            if "request" in data:
                data["request_id"] = data["request"]
            if hasattr(summary, "request") and summary.request:
                data["user_id"] = summary.request.user_id
            return data

        return await self._execute(_get, operation_name="get_summary_by_id", read_only=True)

    async def async_get_summary_context_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary with its request and crawl result in a single read."""

        def _get() -> dict[str, Any] | None:
            row = (
                Summary.select(
                    *aliased_model_fields(Summary, "summary"),
                    *aliased_model_fields(Request, "request"),
                    *aliased_model_fields(CrawlResult, "crawl_result"),
                )
                .join(Request)
                .switch(Request)
                .join(
                    CrawlResult,
                    peewee.JOIN.LEFT_OUTER,
                    on=(CrawlResult.request == Request.id),
                )
                .where(Summary.id == summary_id)
                .dicts()
                .first()
            )
            if row is None:
                return None

            summary_data = extract_aliased_model(row, Summary, "summary")
            request_data = extract_aliased_model(row, Request, "request")
            if summary_data is None or request_data is None:
                return None

            summary_data["request_id"] = summary_data.get("request")
            summary_data["user_id"] = request_data.get("user_id")
            return {
                "summary": summary_data,
                "request": request_data,
                "crawl_result": extract_aliased_model(row, CrawlResult, "crawl_result"),
            }

        return await self._execute(_get, operation_name="get_summary_context_by_id", read_only=True)

    async def async_get_summaries_by_request_ids(
        self, request_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Get summaries by their request IDs."""

        def _get() -> dict[int, dict[str, Any]]:
            if not request_ids:
                return {}
            summaries = Summary.select().where(Summary.request.in_(request_ids))
            result: dict[int, dict[str, Any]] = {}
            for summary in summaries:
                request_id = (
                    summary.request.id if hasattr(summary.request, "id") else summary.request_id
                )
                result[request_id] = model_to_dict(summary) or {}
            return result

        return await self._execute(
            _get, operation_name="get_summaries_by_request_ids", read_only=True
        )

    async def async_get_unread_summaries(
        self,
        user_id: int | None,
        chat_id: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get unread summaries for a user."""

        def _get() -> list[dict[str, Any]]:
            if limit <= 0:
                return []

            topic_query = topic.strip() if topic else None
            base_query = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(~Summary.is_read)
                .order_by(Summary.created_at.asc())
            )

            if user_id is not None:
                base_query = base_query.where(
                    (Request.user_id == user_id) | (Request.user_id.is_null(True))
                )
            if chat_id is not None:
                base_query = base_query.where(
                    (Request.chat_id == chat_id) | (Request.chat_id.is_null(True))
                )

            fetch_limit: int | None = limit
            if topic_query:
                candidate_limit = max(limit * 5, 25)
                topic_request_ids = self._find_topic_search_request_ids(
                    topic_query, candidate_limit=candidate_limit
                )
                if topic_request_ids:
                    fetch_limit = len(topic_request_ids)
                    base_query = base_query.where(Summary.request.in_(topic_request_ids))
                else:
                    fetch_limit = None

            rows_query = base_query if fetch_limit is None else base_query.limit(fetch_limit)

            results: list[dict[str, Any]] = []
            for row in rows_query:
                payload = ensure_mapping(row.json_payload)
                request_data = model_to_dict(row.request) or {}

                if topic_query and not self._summary_matches_topic(
                    payload, request_data, topic_query
                ):
                    continue

                data = model_to_dict(row) or {}
                flattened_request = request_data
                flattened_request.pop("id", None)
                data.update(flattened_request)

                if "request" in data and "request_id" not in data:
                    data["request_id"] = data["request"]

                results.append(data)
                if len(results) >= limit:
                    break
            return results

        return await self._execute(_get, operation_name="get_unread_summaries", read_only=True)

    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Get an unread summary by request ID."""

        def _get() -> dict[str, Any] | None:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where((Summary.request == request_id) & (~Summary.is_read))
                .first()
            )
            if not summary:
                return None
            data = model_to_dict(summary) or {}
            request_data = model_to_dict(summary.request) or {}
            request_data.pop("id", None)
            data.update(request_data)
            if "request" in data and "request_id" not in data:
                data["request_id"] = data["request"]
            return data

        return await self._execute(
            _get, operation_name="get_unread_summary_by_request_id", read_only=True
        )
