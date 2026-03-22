"""Shared helpers for the SQLite summary repository."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import peewee

from app.application.services.topic_search_utils import tokenize
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC, coerce_datetime
from app.db.json_utils import prepare_json_payload
from app.db.models import Summary
from app.domain.models.summary import Summary as DomainSummary

from ._repository_mixin_base import SqliteRepositoryMixinBase

logger = get_logger(__name__)


def _upsert_summary_record(
    *,
    request_id: int,
    lang: str,
    json_payload: dict[str, Any],
    insights_json: dict[str, Any] | None = None,
    is_read: bool = False,
) -> int:
    """Create or update a summary row and return its version."""
    payload = prepare_json_payload(json_payload, default={})
    insights = prepare_json_payload(insights_json)

    try:
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


class SummaryRepositorySharedMixin(SqliteRepositoryMixinBase):
    """Shared helper methods kept on the public summary repository surface."""

    def _find_topic_search_request_ids(
        self, topic: str, *, candidate_limit: int
    ) -> list[int] | None:
        """Search request IDs using the FTS topic index."""
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
            logger.warning("fts_query_failed", extra={"query": fts_query}, exc_info=True)
            return None

        request_ids: list[int] = []
        seen: set[int] = set()
        for row in rows:
            value = None
            if isinstance(row, tuple | list) and row:
                value = row[0]
            elif isinstance(row, Mapping):
                value = row.get("rowid") or row.get("request_id")

            if value is None:
                continue
            try:
                request_id = int(value)
            except (TypeError, ValueError):
                continue
            if request_id not in seen:
                request_ids.append(request_id)
                seen.add(request_id)

        return request_ids

    @staticmethod
    def _sanitize_fts_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        return re.sub(r"\s+", " ", sanitized).strip()

    @staticmethod
    def _summary_matches_topic(
        summary_payload: dict[str, Any], request_data: dict[str, Any], topic: str
    ) -> bool:
        """Check if summary/request matches topic after FTS candidate selection."""
        terms = tokenize(topic)
        if not terms:
            return False

        def _yield_fragments(value: Any) -> Any:
            if isinstance(value, str):
                yield value.casefold()
            elif isinstance(value, list):
                for item in value:
                    yield from _yield_fragments(item)
            elif isinstance(value, dict):
                for key, nested in value.items():
                    yield from _yield_fragments(key)
                    yield from _yield_fragments(nested)

        fragments: list[str] = []
        fragments.extend(_yield_fragments(summary_payload))
        fragments.extend(_yield_fragments(request_data))
        combined = " ".join(fragments)
        return all(term in combined for term in terms)

    def to_domain_model(self, db_summary: dict[str, Any]) -> DomainSummary:
        """Convert a database record to the summary domain model."""
        return DomainSummary(
            id=db_summary.get("id"),
            request_id=db_summary.get("request_id") or db_summary.get("request"),
            content=db_summary.get("json_payload"),
            language=db_summary.get("lang"),
            version=db_summary.get("version", 1),
            is_read=db_summary.get("is_read", False),
            insights=db_summary.get("insights_json"),
            created_at=coerce_datetime(db_summary.get("created_at")),
        )

    def from_domain_model(self, summary: DomainSummary) -> dict[str, Any]:
        """Convert the summary domain model to database field values."""
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
