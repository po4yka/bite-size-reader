"""Summary and unread-query operations for Database facade."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Request, Summary, model_to_dict
from app.services.topic_search_utils import ensure_mapping
from app.services.trending_cache import clear_trending_cache

JSONValue = Mapping[str, Any] | list[Any] | tuple[Any, ...] | str | None


class DatabaseSummaryOpsMixin:
    """Summary CRUD and unread lookup operations."""

    def get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        summary = Summary.get_or_none(Summary.request == request_id)
        data = model_to_dict(summary)
        if data:
            self._convert_bool_fields(data, ["is_read"])
        return data

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_summary_by_request`."""
        return await self._safe_db_operation(
            self.get_summary_by_request,
            request_id,
            operation_name="get_summary_by_request",
            read_only=True,
        )

    def get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary by its ID, including request_id."""
        summary = (
            Summary.select(Summary, Request).join(Request).where(Summary.id == summary_id).first()
        )
        if not summary:
            return None

        data = model_to_dict(summary)
        if data:
            if "request" in data:
                data["request_id"] = data["request"]
            self._convert_bool_fields(data, ["is_read"])
        return data

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_summary_by_id`."""
        return await self._safe_db_operation(
            self.get_summary_by_id,
            summary_id,
            operation_name="get_summary_by_id",
            read_only=True,
        )

    def insert_summary(
        self,
        *,
        request_id: int,
        lang: str | None,
        json_payload: JSONValue,
        insights_json: JSONValue = None,
        version: int = 1,
        is_read: bool = False,
    ) -> int:
        summary = Summary.create(
            request=request_id,
            lang=lang,
            json_payload=self._prepare_json_payload(json_payload),
            insights_json=self._prepare_json_payload(insights_json),
            version=version,
            is_read=is_read,
        )
        self._topic_search.refresh_index(request_id)
        clear_trending_cache()
        return summary.id

    def upsert_summary(
        self,
        *,
        request_id: int,
        lang: str | None,
        json_payload: JSONValue,
        insights_json: JSONValue = None,
        is_read: bool | None = None,
    ) -> int:
        payload_value = self._prepare_json_payload(json_payload)
        insights_value = self._prepare_json_payload(insights_json)
        try:
            summary = Summary.create(
                request=request_id,
                lang=lang,
                json_payload=payload_value,
                insights_json=insights_value,
                version=1,
                is_read=is_read if is_read is not None else False,
            )
            self._topic_search.refresh_index(request_id)
            clear_trending_cache()
            return summary.version
        except peewee.IntegrityError:
            update_map: dict[Any, Any] = {
                Summary.lang: lang,
                Summary.json_payload: payload_value,
                Summary.version: Summary.version + 1,
                Summary.created_at: dt.datetime.now(UTC),
            }
            if insights_value is not None:
                update_map[Summary.insights_json] = insights_value
            if is_read is not None:
                update_map[Summary.is_read] = is_read
            query = Summary.update(update_map).where(Summary.request == request_id)
            query.execute()
            updated = Summary.get_or_none(Summary.request == request_id)
            version_val = updated.version if updated else 0
            self._topic_search.refresh_index(request_id)
            clear_trending_cache()
            return version_val

    async def async_upsert_summary(self, **kwargs: Any) -> int:
        """Asynchronously upsert a summary entry."""
        return await self._safe_db_operation(
            self.upsert_summary,
            operation_name="upsert_summary",
            **kwargs,
        )

    def update_summary_insights(self, request_id: int, insights_json: JSONValue) -> None:
        Summary.update({Summary.insights_json: self._prepare_json_payload(insights_json)}).where(
            Summary.request == request_id
        ).execute()

    def mark_summary_as_read_by_id(self, summary_id: int) -> None:
        """Mark a summary as read by its ID."""
        with self._database.connection_context():
            Summary.update({Summary.is_read: True}).where(Summary.id == summary_id).execute()

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Async wrapper for :meth:`mark_summary_as_read_by_id`."""
        await self._safe_db_operation(
            self.mark_summary_as_read_by_id,
            summary_id,
            operation_name="mark_summary_as_read",
        )

    def mark_summary_as_unread_by_id(self, summary_id: int) -> None:
        """Mark a summary as unread by its ID."""
        with self._database.connection_context():
            Summary.update({Summary.is_read: False}).where(Summary.id == summary_id).execute()

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Async wrapper for :meth:`mark_summary_as_unread_by_id`."""
        await self._safe_db_operation(
            self.mark_summary_as_unread_by_id,
            summary_id,
            operation_name="mark_summary_as_unread",
        )

    def mark_summary_as_read(self, request_id: int) -> None:
        with self._database.connection_context():
            Summary.update({Summary.is_read: True}).where(Summary.request == request_id).execute()

    def get_read_status(self, request_id: int) -> bool:
        summary = Summary.get_or_none(Summary.request == request_id)
        return bool(summary.is_read) if summary else False

    def get_unread_summaries(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return unread summary rows filtered by owner/chat/topic constraints."""
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
            topic_request_ids = self._topic_search.find_request_ids(
                topic_query, candidate_limit=candidate_limit
            )
            if topic_request_ids:
                fetch_limit = len(topic_request_ids)
                base_query = base_query.where(Summary.request.in_(topic_request_ids))
            else:
                fetch_limit = None

        rows_query = base_query
        if fetch_limit is not None:
            rows_query = base_query.limit(fetch_limit)

        results: list[dict[str, Any]] = []
        for row in rows_query:
            payload = ensure_mapping(row.json_payload)
            request_data = model_to_dict(row.request) or {}

            if topic_query and not self._summary_matches_topic(payload, request_data, topic_query):
                continue

            data = model_to_dict(row) or {}
            req_data = request_data
            req_data.pop("id", None)
            data.update(req_data)
            if "request" in data and "request_id" not in data:
                data["request_id"] = data["request"]
            self._convert_bool_fields(data, ["is_read"])
            results.append(data)
            if len(results) >= limit:
                break
        return results

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Async wrapper for :meth:`get_unread_summaries`."""
        return await self._safe_db_operation(
            self.get_unread_summaries,
            user_id=uid,
            chat_id=cid,
            limit=limit,
            topic=topic,
            operation_name="get_unread_summaries",
            read_only=True,
        )

    def get_unread_summary_by_request_id(self, request_id: int) -> dict[str, Any] | None:
        summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where((Summary.request == request_id) & (~Summary.is_read))
            .first()
        )
        if not summary:
            return None
        data = model_to_dict(summary) or {}
        req_data = model_to_dict(summary.request) or {}
        req_data.pop("id", None)
        data.update(req_data)
        if "request" in data and "request_id" not in data:
            data["request_id"] = data["request"]
        self._convert_bool_fields(data, ["is_read"])
        return data
