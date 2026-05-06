"""PostgreSQL topic search index maintenance helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.application.services.topic_search_utils import (
    build_topic_search_document,
    ensure_mapping,
)
from app.db.models import Request, Summary, TopicSearchIndex

if TYPE_CHECKING:
    import logging

    from app.db.session import Database


class TopicSearchIndexManager:
    """Manage PostgreSQL full-text topic search rows."""

    def __init__(self, database: Database, logger: logging.Logger) -> None:
        self._database = database
        self._logger = logger

    async def ensure_index(self) -> None:
        """Rebuild searchable row content.

        Schema creation and GIN index management belong to Alembic; this method
        only synchronizes denormalized search rows from summaries.
        """
        async with self._database.transaction() as session:
            await session.execute(delete(TopicSearchIndex))
            rows = await session.execute(
                select(Summary, Request)
                .join(Request, Summary.request_id == Request.id)
                .where(Summary.json_payload.is_not(None))
            )
            rebuilt = 0
            for summary, request in rows.all():
                document = self._document_from_summary(summary, request)
                if document is None:
                    continue
                await self._write_index(session, document)
                rebuilt += 1
        if rebuilt:
            self._logger.info("topic_search_index_rebuilt", extra={"rows": rebuilt})

    async def refresh_index(self, request_id: int) -> None:
        try:
            async with self._database.transaction() as session:
                row = await session.execute(
                    select(Summary, Request)
                    .join(Request, Summary.request_id == Request.id)
                    .where(Summary.request_id == request_id, Summary.json_payload.is_not(None))
                )
                result = row.first()
                if result is None:
                    await session.execute(
                        delete(TopicSearchIndex).where(TopicSearchIndex.request_id == request_id)
                    )
                    return
                summary, request = result
                document = self._document_from_summary(summary, request)
                if document is None:
                    await session.execute(
                        delete(TopicSearchIndex).where(TopicSearchIndex.request_id == request_id)
                    )
                    return
                await self._write_index(session, document)
        except Exception as exc:
            self._logger.warning(
                "topic_search_index_refresh_failed",
                extra={"request_id": request_id, "error": str(exc)},
            )

    async def find_request_ids(self, topic: str, *, candidate_limit: int) -> list[int] | None:
        query = topic.strip()
        if not query:
            return None
        sql = text(
            """
            SELECT request_id
            FROM topic_search_index
            WHERE body_tsv @@ websearch_to_tsquery('simple', :q)
            ORDER BY ts_rank_cd(body_tsv, websearch_to_tsquery('simple', :q)) DESC
            LIMIT :n
            """
        )
        try:
            async with self._database.session() as session:
                rows = await session.execute(sql, {"q": query, "n": candidate_limit})
        except Exception as exc:
            self._logger.warning("topic_search_index_lookup_failed", extra={"error": str(exc)})
            return None
        request_ids: list[int] = []
        seen: set[int] = set()
        for value in rows.scalars():
            request_id = int(value)
            if request_id in seen:
                continue
            request_ids.append(request_id)
            seen.add(request_id)
        return request_ids

    @staticmethod
    def _document_from_summary(summary: Summary, request: Request) -> Any | None:
        payload = ensure_mapping(summary.json_payload)
        if not payload:
            return None
        request_data = {
            "normalized_url": request.normalized_url,
            "input_url": request.input_url,
            "content_text": request.content_text,
        }
        return build_topic_search_document(
            request_id=request.id,
            payload=payload,
            request_data=request_data,
        )

    @staticmethod
    async def _write_index(session: Any, document: Any) -> None:
        stmt = insert(TopicSearchIndex).values(
            request_id=document.request_id,
            url=document.url or "",
            title=document.title or "",
            snippet=document.snippet or "",
            source=document.source or "",
            published_at=document.published_at or "",
            body=document.body,
            tags=document.tags_text or "",
        )
        update_values = {
            "url": stmt.excluded.url,
            "title": stmt.excluded.title,
            "snippet": stmt.excluded.snippet,
            "source": stmt.excluded.source,
            "published_at": stmt.excluded.published_at,
            "body": stmt.excluded.body,
            "tags": stmt.excluded.tags,
        }
        await session.execute(stmt.on_conflict_do_update(index_elements=["request_id"], set_=update_values))
