"""Topic search index maintenance helpers."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import peewee

from app.db.models import Request, Summary, TopicSearchIndex
from app.services.topic_search_utils import (
    TopicSearchDocument,
    build_topic_search_document,
    ensure_mapping,
    tokenize,
)

if TYPE_CHECKING:
    import logging


class TopicSearchIndexRebuiltError(RuntimeError):
    """Raised to signal that the topic search index was rebuilt mid-operation."""


class TopicSearchIndexManager:
    """Manage the FTS topic search index lifecycle."""

    def __init__(self, database: peewee.SqliteDatabase, logger: logging.Logger) -> None:
        self._database = database
        self._logger = logger
        self._delete_warned = False
        self._reset_in_progress = False

    def ensure_index(self) -> None:
        table_name = TopicSearchIndex._meta.table_name
        with self._database.connection_context():
            tables = set(self._database.get_tables())
            if table_name not in tables:
                TopicSearchIndex.create_table()
                self._rebuild_index()
                return
            try:
                summary_count = Summary.select().where(Summary.json_payload.is_null(False)).count()
                index_count = TopicSearchIndex.select().count()
            except peewee.DatabaseError as exc:  # pragma: no cover - defensive path
                self._logger.warning("topic_search_index_count_failed", extra={"error": str(exc)})
                summary_count = -1
                index_count = -2

            if summary_count < 0 or index_count != summary_count:
                try:
                    self._rebuild_index()
                except TopicSearchIndexRebuiltError:
                    return

    def refresh_index(self, request_id: int) -> None:
        try:
            with self._database.connection_context():
                summary = (
                    Summary.select(Summary, Request)
                    .join(Request)
                    .where((Summary.request == request_id) & (Summary.json_payload.is_null(False)))
                    .first()
                )
                if not summary:
                    self._remove_entry(request_id)
                    return

                payload = ensure_mapping(summary.json_payload)
                if not payload:
                    self._remove_entry(request_id)
                    return

                request_data = {
                    "normalized_url": getattr(summary.request, "normalized_url", None),
                    "input_url": getattr(summary.request, "input_url", None),
                    "content_text": getattr(summary.request, "content_text", None),
                }
                document = build_topic_search_document(
                    request_id=request_id,
                    payload=payload,
                    request_data=request_data,
                )
                if not document:
                    self._remove_entry(request_id)
                    return

                try:
                    self._write_index(document)
                except TopicSearchIndexRebuiltError:
                    return
        except Exception as exc:
            self._logger.warning(
                "topic_search_index_refresh_failed",
                extra={"request_id": request_id, "error": str(exc)},
            )

    def find_request_ids(self, topic: str, *, candidate_limit: int) -> list[int] | None:
        terms = tokenize(topic)

        if not terms:
            sanitized = self._sanitize_term(topic.casefold())
            if not sanitized:
                return None
            fts_query = f'"{sanitized}"*'
        else:
            sanitized_terms = [self._sanitize_term(term) for term in terms]
            sanitized_terms = [term for term in sanitized_terms if term]
            if not sanitized_terms:
                return None
            phrase = self._sanitize_term(" ".join(terms))
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
            with self._database.connection_context():
                cursor = self._database.execute_sql(sql, (fts_query, candidate_limit))
                rows = list(cursor)
        except Exception as exc:
            self._logger.warning("topic_search_index_lookup_failed", extra={"error": str(exc)})
            return None

        request_ids: list[int] = []
        seen: set[int] = set()
        for row in rows:
            value: Any | None = None
            if isinstance(row, Mapping):
                value = row.get("rowid") or row.get("request_id")
            elif hasattr(row, "keys"):
                try:
                    value = row["rowid"]
                except (KeyError, TypeError, IndexError):
                    try:
                        value = row["request_id"]
                    except (KeyError, TypeError, IndexError):
                        value = None
            if value is None:
                try:
                    value = row[0]
                except (KeyError, TypeError, IndexError):
                    value = None
            if value is None:
                continue
            try:
                request_id = int(value)
            except (TypeError, ValueError):
                continue
            if request_id in seen:
                continue
            request_ids.append(request_id)
            seen.add(request_id)

        return request_ids

    @staticmethod
    def _sanitize_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        return re.sub(r"\s+", " ", sanitized).strip()

    def _write_index(self, document: TopicSearchDocument) -> None:
        self._delete_row(document.request_id)
        self._database.execute_sql(
            """
            INSERT INTO topic_search_index(
                rowid, request_id, url, title, snippet, source, published_at, body, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.request_id,
                str(document.request_id),
                document.url or "",
                document.title or "",
                document.snippet or "",
                document.source or "",
                document.published_at or "",
                document.body,
                document.tags_text or "",
            ),
        )

    def _remove_entry(self, request_id: int) -> None:
        self._delete_row(request_id)

    def _rebuild_index(self) -> None:
        with self._database.connection_context():
            self._clear_index()
            rows = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(Summary.json_payload.is_null(False))
            )
            rebuilt = 0
            try:
                for row in rows.iterator():
                    payload = ensure_mapping(row.json_payload)
                    if not payload:
                        continue
                    request_data = {
                        "normalized_url": getattr(row.request, "normalized_url", None),
                        "input_url": getattr(row.request, "input_url", None),
                        "content_text": getattr(row.request, "content_text", None),
                    }
                    document = build_topic_search_document(
                        request_id=row.request.id,
                        payload=payload,
                        request_data=request_data,
                    )
                    if not document:
                        continue
                    self._write_index(document)
                    rebuilt += 1
            except TopicSearchIndexRebuiltError:
                return
        if rebuilt:
            self._logger.info("topic_search_index_rebuilt", extra={"rows": rebuilt})

    def _clear_index(self) -> None:
        """Remove all rows from the topic search FTS index."""
        self._database.execute_sql(
            "INSERT INTO topic_search_index(topic_search_index) VALUES ('delete-all')"
        )

    def _delete_row(self, rowid: int) -> None:
        """Remove a single row from the topic search FTS index."""
        try:
            self._database.execute_sql(
                "DELETE FROM topic_search_index WHERE rowid = ?",
                (rowid,),
            )
        except peewee.DatabaseError as exc:
            message = str(exc)
            if "malformed" in message.lower():
                self._handle_index_error(exc, rowid)
                return

            self._log_delete_fallback(rowid, message)

    def _log_delete_fallback(self, rowid: int, message: str) -> None:
        """Log degraded delete path, but only warn once to avoid noise."""
        log_extra = {"rowid": rowid, "error": message}
        if not self._delete_warned:
            self._delete_warned = True
            self._logger.warning("topic_search_index_delete_failed_primary", extra=log_extra)
        else:  # pragma: no cover - logging noise suppression
            self._logger.warning("topic_search_index_delete_failed_primary", extra=log_extra)

    def _handle_index_error(self, exc: peewee.DatabaseError, rowid: int) -> None:
        """Handle unrecoverable FTS errors by rebuilding the index."""
        message = str(exc)
        self._logger.error(
            "topic_search_index_delete_failed",
            extra={"rowid": rowid, "error": message},
        )
        if "malformed" not in message.lower():
            raise exc

        self._reset_index()
        raise TopicSearchIndexRebuiltError from exc

    def _reset_index(self) -> None:
        """Drop and rebuild the topic search index to recover from corruption."""
        if self._reset_in_progress:
            return
        self._reset_in_progress = True
        try:
            with self._database.connection_context():
                with contextlib.suppress(peewee.DatabaseError):
                    TopicSearchIndex.drop_table(safe=True)
                TopicSearchIndex.create_table()
            try:
                self._rebuild_index()
            except TopicSearchIndexRebuiltError:
                return
        except peewee.DatabaseError as reset_exc:  # pragma: no cover - defensive
            self._logger.exception(
                "topic_search_index_reset_failed",
                extra={"error": str(reset_exc)},
            )
        finally:
            self._reset_in_progress = False
