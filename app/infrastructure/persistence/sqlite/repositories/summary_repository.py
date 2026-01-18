"""SQLite implementation of summary repository.

This adapter translates between domain Summary models and database records.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Request, Summary, model_to_dict
from app.db.utils import prepare_json_payload
from app.domain.models.summary import Summary as DomainSummary
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository
from app.services.topic_search_utils import ensure_mapping, tokenize


class SqliteSummaryRepositoryAdapter(SqliteBaseRepository):
    """Adapter that implements SummaryRepository using Peewee models directly.

    This replaces the legacy delegation to the monolithic Database class.
    """

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary."""

        def _upsert() -> int:
            payload = prepare_json_payload(json_payload, default={})
            insights = prepare_json_payload(insights_json)

            try:
                # Try to create new summary
                summary = Summary.create(
                    request=request_id,
                    lang=lang,
                    json_payload=payload,
                    insights_json=insights,
                    is_read=is_read,
                    version=1,
                )
                return summary.version
            except peewee.IntegrityError:
                # Update existing summary
                Summary.update(
                    {
                        Summary.lang: lang,
                        Summary.json_payload: payload,
                        Summary.insights_json: insights,
                        Summary.version: Summary.version + 1,
                        Summary.is_read: is_read,
                        Summary.updated_at: datetime.now(UTC),
                    }
                ).where(Summary.request == request_id).execute()

                summary = Summary.get_or_none(Summary.request == request_id)
                return summary.version if summary else 1

        return await self._execute(_upsert, operation_name="upsert_summary")

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

            # Apply filters
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

            # Apply sorting
            if sort == "created_at_desc":
                query = query.order_by(Request.created_at.desc())
            else:
                query = query.order_by(Request.created_at.asc())

            total_summaries = query.count()

            summaries_list = []
            for row in query.limit(limit).offset(offset):
                summaries_list.append(model_to_dict(row))

            # Unread count
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
        """Get a summary ID by its request ID.

        Args:
            request_id: The request ID to search for

        Returns:
            Summary ID if found, None otherwise
        """

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
            return data

        return await self._execute(_get, operation_name="get_summary_by_id", read_only=True)

    async def async_get_summaries_by_request_ids(
        self, request_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Get summaries by their request IDs.

        Returns:
            Dict mapping request_id to summary data.
        """

        def _get() -> dict[int, dict[str, Any]]:
            if not request_ids:
                return {}
            summaries = Summary.select().where(Summary.request.in_(request_ids))
            result = {}
            for s in summaries:
                req_id = s.request.id if hasattr(s.request, "id") else s.request_id
                result[req_id] = model_to_dict(s) or {}
            return result

        return await self._execute(
            _get, operation_name="get_summaries_by_request_ids", read_only=True
        )

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
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

            if uid is not None:
                base_query = base_query.where(
                    (Request.user_id == uid) | (Request.user_id.is_null(True))
                )
            if cid is not None:
                base_query = base_query.where(
                    (Request.chat_id == cid) | (Request.chat_id.is_null(True))
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

            rows_query = base_query
            if fetch_limit is not None:
                rows_query = base_query.limit(fetch_limit)

            results: list[dict[str, Any]] = []
            for row in rows_query:
                payload = ensure_mapping(row.json_payload)
                request_data = model_to_dict(row.request) or {}

                if topic_query and not self._summary_matches_topic(
                    payload, request_data, topic_query
                ):
                    continue

                data = model_to_dict(row) or {}
                req_data = request_data
                req_data.pop("id", None)
                data.update(req_data)

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
            req_data = model_to_dict(summary.request) or {}
            req_data.pop("id", None)
            data.update(req_data)
            if "request" in data and "request_id" not in data:
                data["request_id"] = data["request"]
            return data

        return await self._execute(
            _get, operation_name="get_unread_summary_by_request_id", read_only=True
        )

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark a summary as read."""

        def _update() -> None:
            Summary.update({Summary.is_read: True}).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="mark_summary_as_read")

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Mark a summary as unread."""

        def _update() -> None:
            Summary.update({Summary.is_read: False}).where(Summary.id == summary_id).execute()

        await self._execute(_update, operation_name="mark_summary_as_unread")

    async def async_update_summary_insights(
        self, request_id: int, insights_json: dict[str, Any]
    ) -> None:
        """Update the insights field of a summary."""

        def _update() -> None:
            insights = prepare_json_payload(insights_json)
            Summary.update({Summary.insights_json: insights}).where(
                Summary.request == request_id
            ).execute()

        await self._execute(_update, operation_name="update_summary_insights")

    async def async_soft_delete_summary(self, summary_id: int) -> None:
        """Soft delete a summary."""

        def _update() -> None:
            Summary.update({Summary.is_deleted: True, Summary.deleted_at: datetime.now(UTC)}).where(
                Summary.id == summary_id
            ).execute()

        await self._execute(_update, operation_name="soft_delete_summary")

    async def async_toggle_favorite(self, summary_id: int) -> bool:
        """Toggle favorite status of a summary."""

        def _toggle() -> bool:
            summary = Summary.get_by_id(summary_id)
            new_val = not summary.is_favorited
            summary.is_favorited = new_val
            summary.save()
            return new_val

        return await self._execute(_toggle, operation_name="toggle_favorite")

    # Private Helpers

    def _find_topic_search_request_ids(
        self, topic: str, *, candidate_limit: int
    ) -> list[int] | None:
        """Search request IDs using FTS index."""
        terms = tokenize(topic)
        if not terms:
            sanitized = self._sanitize_fts_term(topic.casefold())
            if not sanitized:
                return None
            fts_query = f'"{sanitized}"*'
        else:
            sanitized_terms = [self._sanitize_fts_term(term) for term in terms]
            sanitized_terms = [term for term in sanitized_terms if term]
            if not sanitized_terms:
                return None
            phrase = self._sanitize_fts_term(" ".join(terms))
            components: list[str] = []
            wildcard_terms = [f'"{term}"*' for term in sanitized_terms]
            if wildcard_terms:
                components.append(" AND ".join(wildcard_terms))
            if phrase:
                components.append(f'"{phrase}"')
            fts_query = " OR ".join(component for component in components if component)
            if not fts_query:
                return None

        sql = (
            "SELECT rowid FROM topic_search_index "
            "WHERE topic_search_index MATCH ? "
            "ORDER BY bm25(topic_search_index) ASC "
            "LIMIT ?"
        )

        try:
            cursor = self._session.database.execute_sql(sql, (fts_query, candidate_limit))
            rows = list(cursor)
        except Exception:
            return None

        request_ids: list[int] = []
        seen: set[int] = set()
        for row in rows:
            value = None
            if isinstance(row, tuple | list) and row:
                value = row[0]
            elif isinstance(row, Mapping):
                value = row.get("rowid") or row.get("request_id")

            if value is not None:
                try:
                    rid = int(value)
                    if rid not in seen:
                        request_ids.append(rid)
                        seen.add(rid)
                except (TypeError, ValueError):
                    pass

        return request_ids

    @staticmethod
    def _sanitize_fts_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        return re.sub(r"\s+", " ", sanitized).strip()

    @staticmethod
    def _summary_matches_topic(
        summary_payload: dict[str, Any], request_data: dict[str, Any], topic: str
    ) -> bool:
        """Check if summary/request matches topic (software filtering)."""
        terms = tokenize(topic)
        if not terms:
            return False

        def _yield_fragments(val: Any) -> Any:
            if isinstance(val, str):
                yield val.casefold()
            elif isinstance(val, list):
                for item in val:
                    yield from _yield_fragments(item)
            elif isinstance(val, dict):
                for k, v in val.items():
                    yield from _yield_fragments(k)
                    yield from _yield_fragments(v)

        fragments: list[str] = []
        fragments.extend(_yield_fragments(summary_payload))
        fragments.extend(_yield_fragments(request_data))

        combined = " ".join(fragments)
        return all(term in combined for term in terms)

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all summaries for a user (for sync operations).

        Returns:
            List of summary dicts with request_id flattened.
        """

        def _get() -> list[dict[str, Any]]:
            summaries = (
                Summary.select(Summary, Request).join(Request).where(Request.user_id == user_id)
            )
            result = []
            for s in summaries:
                s_dict = model_to_dict(s) or {}
                # Flatten request to just the ID for sync
                if "request" in s_dict and isinstance(s_dict["request"], dict):
                    s_dict["request"] = s_dict["request"]["id"]
                result.append(s_dict)
            return result

        return await self._execute(
            _get, operation_name="get_all_summaries_for_user", read_only=True
        )

    async def async_get_summary_for_sync_apply(
        self, summary_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """Get a summary by ID for sync apply, validating user ownership.

        Returns:
            Summary dict or None if not found/not owned.
        """

        def _get() -> dict[str, Any] | None:
            summary = (
                Summary.select(Summary, Request)
                .join(Request)
                .where((Summary.id == summary_id) & (Request.user_id == user_id))
                .first()
            )
            if not summary:
                return None
            return model_to_dict(summary) or {}

        return await self._execute(
            _get, operation_name="get_summary_for_sync_apply", read_only=True
        )

    async def async_apply_sync_change(
        self,
        summary_id: int,
        *,
        is_deleted: bool | None = None,
        deleted_at: datetime | None = None,
        is_read: bool | None = None,
    ) -> int:
        """Apply a sync change to a summary.

        Returns:
            The new server_version after the update.
        """

        def _apply() -> int:
            update_fields: dict[Any, Any] = {}
            if is_deleted is not None:
                update_fields[Summary.is_deleted] = is_deleted
            if deleted_at is not None:
                update_fields[Summary.deleted_at] = deleted_at
            if is_read is not None:
                update_fields[Summary.is_read] = is_read

            if update_fields:
                Summary.update(update_fields).where(Summary.id == summary_id).execute()

            # Fetch updated summary to get server_version
            summary = Summary.get_or_none(Summary.id == summary_id)
            return int(summary.server_version or 0) if summary else 0

        return await self._execute(_apply, operation_name="apply_sync_change")

    def to_domain_model(self, db_summary: dict[str, Any]) -> DomainSummary:
        """Convert database record to domain model."""
        return DomainSummary(
            id=db_summary.get("id"),
            request_id=db_summary.get("request_id") or db_summary.get("request"),
            content=db_summary.get("json_payload"),
            language=db_summary.get("lang"),
            version=db_summary.get("version", 1),
            is_read=db_summary.get("is_read", False),
            insights=db_summary.get("insights_json"),
            created_at=db_summary.get("created_at", datetime.now(UTC)),
        )

    def from_domain_model(self, summary: DomainSummary) -> dict[str, Any]:
        """Convert domain model to database record format."""
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
