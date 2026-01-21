"""SQLite implementation of topic search repository.

This adapter handles FTS index maintenance and search operations.
"""

from __future__ import annotations

import operator
import re
from functools import reduce
from typing import TYPE_CHECKING, Any

import peewee

from app.db.models import Request, Summary, TopicSearchIndex, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository
from app.services.topic_search_utils import (
    TopicSearchDocument,
    build_snippet,
    build_topic_search_document,
    clean_snippet,
    compose_search_body,
    ensure_mapping,
    normalize_text,
    tokenize,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class TopicSearchIndexRebuiltError(RuntimeError):
    """Raised to signal that the topic search index was rebuilt mid-operation."""


class SqliteTopicSearchRepositoryAdapter(SqliteBaseRepository):
    """Adapter for Topic Search Index operations."""

    async def async_ensure_index(self) -> None:
        """Ensure the topic search index exists, rebuilding if necessary."""

        def _ensure() -> None:
            if not self._session.database.table_exists(TopicSearchIndex._meta.table_name):
                self._session.database.create_tables([TopicSearchIndex])
                self._rebuild_topic_search_index()

        await self._execute(_ensure, operation_name="ensure_topic_search_index")

    async def async_write_document(self, document: TopicSearchDocument) -> None:
        """Write a document to the search index."""

        def _write() -> None:
            self._write_topic_search_index(document)

        await self._execute(_write, operation_name="write_topic_search_index")

    async def async_refresh_index(self, request_id: int) -> None:
        """Refresh index for a specific request."""

        def _refresh() -> None:
            self._refresh_topic_search_index(request_id)

        await self._execute(_refresh, operation_name="refresh_topic_search_index")

    async def async_rebuild_index(self) -> None:
        """Rebuild the entire search index."""

        def _rebuild() -> None:
            self._rebuild_topic_search_index()

        await self._execute(_rebuild, operation_name="rebuild_topic_search_index")

    async def async_reset_index(self) -> None:
        """Drop and rebuild the topic search index to recover from corruption."""

        def _reset() -> None:
            self._reset_topic_search_index()

        await self._execute(_reset, operation_name="reset_topic_search_index")

    async def async_search_request_ids(
        self, topic: str, *, candidate_limit: int = 100
    ) -> list[int] | None:
        """Find request IDs matching the topic using FTS."""

        def _search() -> list[int] | None:
            return self._find_topic_search_request_ids(topic, candidate_limit=candidate_limit)

        return await self._execute(
            _search, operation_name="search_topic_request_ids", read_only=True
        )

    async def async_fts_search_paginated(
        self, query: str, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Perform FTS5 search with pagination.

        Returns:
            Tuple of (results list, total count).
            Each result has: request_id, title, snippet, source, published_at.
        """

        def _search() -> tuple[list[dict[str, Any]], int]:
            search_query = TopicSearchIndex.search(query).order_by(TopicSearchIndex.rank)
            total = search_query.count()
            results = []
            for row in search_query.limit(limit).offset(offset):
                results.append(
                    {
                        "request_id": row.request_id,
                        "title": row.title,
                        "snippet": row.snippet,
                        "source": row.source,
                        "published_at": row.published_at,
                    }
                )
            return results, total

        return await self._execute(_search, operation_name="fts_search_paginated", read_only=True)

    async def async_search_documents(
        self, topic: str, limit: int = 10
    ) -> list[TopicSearchDocument]:
        """Search documents using FTS index."""

        def _search() -> list[TopicSearchDocument]:
            return self._search_documents_via_index(topic, limit)

        return await self._execute(_search, operation_name="search_topic_documents", read_only=True)

    async def async_scan_documents(
        self,
        terms: Sequence[str],
        normalized_query: str,
        seen_urls: set[str],
        limit: int,
        max_scan: int | None = None,
    ) -> list[TopicSearchDocument]:
        """Scan summaries table for documents matching terms (fallback)."""

        def _scan() -> list[TopicSearchDocument]:
            return self._scan_summaries(
                terms=terms,
                normalized_query=normalized_query,
                seen_urls=seen_urls,
                limit=limit,
                max_scan=max_scan,
            )

        return await self._execute(_scan, operation_name="scan_topic_documents", read_only=True)

    # Private implementations copied from Database class and LocalTopicSearchService

    def _write_topic_search_index(self, document: TopicSearchDocument) -> None:
        TopicSearchIndex.insert(
            request_id=document.request_id,
            url=document.url,
            title=document.title,
            snippet=document.snippet,
            source=document.source,
            published_at=document.published_at,
            body=document.body,
            tags=document.tags_text,
        ).execute()

    def _refresh_topic_search_index(self, request_id: int) -> None:
        self._remove_topic_search_index_entry(request_id)

        row = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(Summary.request == request_id)
            .first()
        )
        if not row:
            return

        payload = ensure_mapping(row.json_payload)
        request_data = model_to_dict(row.request) or {}

        doc = build_topic_search_document(
            request_id=request_id, payload=payload, request_data=request_data
        )
        if doc:
            self._write_topic_search_index(doc)

    def _remove_topic_search_index_entry(self, request_id: int) -> None:
        TopicSearchIndex.delete().where(TopicSearchIndex.request_id == request_id).execute()

    def _rebuild_topic_search_index(self) -> None:
        batch: list[dict[str, Any]] = []
        batch_size = 250

        def _flush_batch(items: list[dict[str, Any]]) -> None:
            if not items:
                return
            TopicSearchIndex.insert_many(items).execute()
            items.clear()

        # Wrap in atomic transaction for atomicity - either full rebuild succeeds
        # or rolls back completely, avoiding partial index states on error.
        with self._session.database.atomic():
            self._clear_topic_search_index()
            query = Summary.select(Summary, Request).join(Request).iterator()

            for row in query:
                payload = ensure_mapping(row.json_payload)
                request_data = model_to_dict(row.request) or {}
                doc = build_topic_search_document(
                    request_id=row.request_id, payload=payload, request_data=request_data
                )
                if not doc:
                    continue
                batch.append(
                    {
                        "request_id": doc.request_id,
                        "url": doc.url,
                        "title": doc.title,
                        "snippet": doc.snippet,
                        "source": doc.source,
                        "published_at": doc.published_at,
                        "body": doc.body,
                        "tags": doc.tags_text,
                    }
                )
                if len(batch) >= batch_size:
                    _flush_batch(batch)

            _flush_batch(batch)

    def _clear_topic_search_index(self) -> None:
        TopicSearchIndex.delete().execute()

    def _find_topic_search_request_ids(
        self, topic: str, *, candidate_limit: int
    ) -> list[int] | None:
        fts_query = self._build_fts_query(topic)
        if not fts_query:
            return None

        sql = (
            f"SELECT request_id FROM {TopicSearchIndex._meta.table_name} "
            f"WHERE {TopicSearchIndex._meta.table_name} MATCH ? "
            f"ORDER BY bm25({TopicSearchIndex._meta.table_name}) ASC "
            f"LIMIT ?"
        )

        try:
            cursor = self._session.database.execute_sql(sql, (fts_query, candidate_limit))
            rows = list(cursor)
        except Exception as exc:
            # Log FTS query failures for debugging - may indicate index corruption
            import logging

            logging.getLogger(__name__).debug(
                "topic_search_fts_query_failed",
                extra={
                    "fts_query": fts_query,
                    "candidate_limit": candidate_limit,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return None

        request_ids: list[int] = []
        seen: set[int] = set()
        for row in rows:
            val = row[0] if row else None
            if val is not None:
                try:
                    rid = int(val)
                    if rid not in seen:
                        request_ids.append(rid)
                        seen.add(rid)
                except (ValueError, TypeError):
                    pass
        return request_ids

    def _search_documents_via_index(self, topic: str, limit: int) -> list[TopicSearchDocument]:
        fts_query = self._build_fts_query(topic)
        if not fts_query:
            return []

        candidate_limit = max(limit * 5, 25)
        # We select specific columns matching TopicSearchDocument
        sql = (
            "SELECT request_id, url, title, snippet, source, published_at, body, tags "
            f"FROM {TopicSearchIndex._meta.table_name} "
            f"WHERE {TopicSearchIndex._meta.table_name} MATCH ? "
            f"ORDER BY bm25({TopicSearchIndex._meta.table_name}) ASC "
            f"LIMIT ?"
        )

        documents: list[TopicSearchDocument] = []
        seen_urls: set[str] = set()

        try:
            cursor = self._session.database.execute_sql(sql, (fts_query, candidate_limit))
            rows = list(cursor)
        except Exception as exc:
            # Log FTS search failures for debugging - may indicate index corruption
            import logging

            logging.getLogger(__name__).debug(
                "topic_search_documents_fts_failed",
                extra={
                    "fts_query": fts_query,
                    "candidate_limit": candidate_limit,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return []

        for row in rows:
            # Map row to TopicSearchDocument
            # Assuming row order matches SELECT
            try:
                request_id = int(row[0])
                url = normalize_text(row[1])
                if not url or url in seen_urls:
                    continue

                doc = TopicSearchDocument(
                    request_id=request_id,
                    url=url,
                    title=normalize_text(row[2]) or url,
                    snippet=clean_snippet(row[3]),
                    source=normalize_text(row[4]),
                    published_at=normalize_text(row[5]),
                    body=row[6] or "",  # body
                    tags_text=row[7],  # tags
                )
                documents.append(doc)
                seen_urls.add(url)
                if len(documents) >= limit:
                    break
            except (ValueError, TypeError, IndexError):
                continue

        return documents

    def _scan_summaries(
        self,
        *,
        terms: Sequence[str],
        normalized_query: str,
        seen_urls: set[str],
        limit: int,
        max_scan: int | None,
    ) -> list[TopicSearchDocument]:
        if limit <= 0:
            return []

        documents: list[TopicSearchDocument] = []

        query = (
            Summary.select(
                Summary.request,
                Summary.json_payload,
                Request.normalized_url,
                Request.input_url,
                Request.content_text,
            )
            .join(Request)
            .where(Summary.json_payload.is_null(False))
            .order_by(Summary.created_at.desc())
        )
        if terms:
            term_conditions = []
            for term in terms:
                term_conditions.extend(
                    [
                        Request.content_text.contains(term),
                        Request.normalized_url.contains(term),
                        Request.input_url.contains(term),
                    ]
                )
            if term_conditions:
                query = query.where(reduce(operator.or_, term_conditions))
        if max_scan:
            query = query.limit(max_scan)

        for row in query.dicts():
            payload = ensure_mapping(row.get("json_payload"))
            metadata = ensure_mapping(payload.get("metadata"))

            url = (
                normalize_text(metadata.get("canonical_url"))
                or normalize_text(metadata.get("url"))
                or normalize_text(row.get("normalized_url"))
                or normalize_text(row.get("input_url"))
            )
            if not url or url in seen_urls:
                continue

            title = (
                normalize_text(metadata.get("title")) or normalize_text(payload.get("title")) or url
            )

            haystack, tags_text = compose_search_body(
                title=title,
                payload=payload,
                metadata=metadata,
                content_text=row.get("content_text"),
            )

            if not self._matches(terms, normalized_query, haystack):
                continue

            request_id = row.get("request")
            if request_id is None:
                continue

            doc = TopicSearchDocument(
                request_id=int(request_id),
                url=url,
                title=title,
                snippet=build_snippet(payload),
                source=normalize_text(metadata.get("domain") or metadata.get("source")),
                published_at=normalize_text(
                    metadata.get("published_at")
                    or metadata.get("published")
                    or metadata.get("last_updated")
                ),
                body=haystack,
                tags_text=tags_text,
            )

            documents.append(doc)
            seen_urls.add(url)
            if len(documents) >= limit:
                break

        return documents

    def _build_fts_query(self, topic: str) -> str | None:
        terms = tokenize(topic)
        if not terms:
            sanitized = self._sanitize_fts_term(topic.casefold())
            if not sanitized:
                return None
            return f'"{sanitized}"*'

        sanitized_terms = [self._sanitize_fts_term(term) for term in terms]
        sanitized_terms = [term for term in sanitized_terms if term]
        if not sanitized_terms:
            return None

        phrase = self._sanitize_fts_term(" ".join(terms))
        wildcard_terms = [f'"{term}"*' for term in sanitized_terms]
        components = [" AND ".join(wildcard_terms)]
        if phrase:
            components.append(f'"{phrase}"')
        return " OR ".join(component for component in components if component)

    @staticmethod
    def _matches(terms: Sequence[str], normalized_query: str, haystack: str) -> bool:
        if not haystack:
            return False
        if not terms:
            return normalized_query in haystack
        return all(term in haystack for term in terms)

    @staticmethod
    def _sanitize_fts_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        return re.sub(r"\s+", " ", sanitized).strip()

    def _delete_topic_search_index_row(self, rowid: int) -> None:
        """Remove a single row from the topic search FTS index."""
        try:
            self._session.database.execute_sql(
                "DELETE FROM topic_search_index WHERE rowid = ?",
                (rowid,),
            )
        except peewee.DatabaseError as exc:
            if "malformed" in str(exc).lower():
                self._reset_topic_search_index()
                raise TopicSearchIndexRebuiltError from exc
            raise

    def _reset_topic_search_index(self) -> None:
        """Drop and rebuild the topic search index to recover from corruption."""
        import logging

        try:
            self._session.database.execute_sql("DROP TABLE IF EXISTS topic_search_index")
            TopicSearchIndex.create_table()
            self._rebuild_topic_search_index()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "topic_search_index_reset_failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
