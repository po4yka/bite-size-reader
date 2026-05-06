"""SQLAlchemy implementation of the embedding repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Request, Summary, SummaryEmbedding, model_to_dict
from app.db.types import _utcnow

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteEmbeddingRepositoryAdapter:
    """Adapter for summary embedding operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_get_all_embeddings(self) -> list[dict[str, Any]]:
        """Fetch all embeddings with metadata from database."""
        async with self._database.session() as session:
            rows = await session.execute(
                select(SummaryEmbedding, Summary, Request)
                .join(Summary, SummaryEmbedding.summary_id == Summary.id)
                .join(Request, Summary.request_id == Request.id)
                .order_by(SummaryEmbedding.id)
            )
            return [_embedding_row(row[0], row[1], row[2]) for row in rows]

    async def async_get_embeddings_by_request_ids(
        self,
        request_ids: list[int],
    ) -> list[dict[str, Any]]:
        """Fetch embeddings scoped to specific request IDs."""
        if not request_ids:
            return []
        async with self._database.session() as session:
            rows = await session.execute(
                select(SummaryEmbedding, Summary, Request)
                .join(Summary, SummaryEmbedding.summary_id == Summary.id)
                .join(Request, Summary.request_id == Request.id)
                .where(Request.id.in_(request_ids))
                .order_by(SummaryEmbedding.id)
            )
            return [_embedding_row(row[0], row[1], row[2]) for row in rows]

    async def async_get_recent_embeddings(self, *, limit: int) -> list[dict[str, Any]]:
        """Fetch the most recent embeddings bounded by a hard limit."""
        if limit <= 0:
            return []
        async with self._database.session() as session:
            rows = await session.execute(
                select(SummaryEmbedding, Summary, Request)
                .join(Summary, SummaryEmbedding.summary_id == Summary.id)
                .join(Request, Summary.request_id == Request.id)
                .order_by(Request.created_at.desc())
                .limit(limit)
            )
            return [_embedding_row(row[0], row[1], row[2]) for row in rows]

    async def async_create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Store or update embedding for a summary."""
        async with self._database.transaction() as session:
            stmt = (
                insert(SummaryEmbedding)
                .values(
                    summary_id=summary_id,
                    embedding_blob=embedding_blob,
                    model_name=model_name,
                    model_version=model_version,
                    dimensions=dimensions,
                    language=language,
                )
                .on_conflict_do_update(
                    index_elements=[SummaryEmbedding.summary_id],
                    set_={
                        "embedding_blob": embedding_blob,
                        "model_name": model_name,
                        "model_version": model_version,
                        "dimensions": dimensions,
                        "language": language,
                        "created_at": _utcnow(),
                    },
                )
            )
            await session.execute(stmt)

    async def async_get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Retrieve embedding for a summary."""
        async with self._database.session() as session:
            embedding = await session.scalar(
                select(SummaryEmbedding).where(SummaryEmbedding.summary_id == summary_id)
            )
            return model_to_dict(embedding)


def _embedding_row(
    embedding: SummaryEmbedding,
    summary: Summary,
    request: Request,
) -> dict[str, Any]:
    return {
        "request_id": request.id,
        "summary_id": summary.id,
        "embedding_blob": embedding.embedding_blob,
        "json_payload": summary.json_payload,
        "normalized_url": request.normalized_url,
        "input_url": request.input_url,
    }
