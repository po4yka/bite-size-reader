"""SQLite implementation of embedding repository.

This adapter handles persistence for vector embeddings used in semantic search.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Request, Summary, SummaryEmbedding, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteEmbeddingRepositoryAdapter(SqliteBaseRepository):
    """Adapter for summary embedding operations."""

    async def async_get_all_embeddings(self) -> list[dict[str, Any]]:
        """Fetch all embeddings with metadata from database."""

        def _query() -> list[dict[str, Any]]:
            results = []
            query = (
                SummaryEmbedding.select(SummaryEmbedding, Summary, Request)
                .join(Summary)
                .join(Request)
            )

            for row in query:
                results.append(
                    {
                        "request_id": row.summary.request.id,
                        "summary_id": row.summary.id,
                        "embedding_blob": row.embedding_blob,
                        "json_payload": row.summary.json_payload,
                        "normalized_url": row.summary.request.normalized_url,
                        "input_url": row.summary.request.input_url,
                    }
                )
            return results

        return await self._execute(_query, operation_name="get_all_embeddings", read_only=True)

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

        def _upsert() -> None:
            try:
                # Try to create new embedding
                SummaryEmbedding.create(
                    summary=summary_id,
                    embedding_blob=embedding_blob,
                    model_name=model_name,
                    model_version=model_version,
                    dimensions=dimensions,
                    language=language,
                )
            except peewee.IntegrityError:
                # Embedding exists, update it
                SummaryEmbedding.update(
                    {
                        SummaryEmbedding.embedding_blob: embedding_blob,
                        SummaryEmbedding.model_name: model_name,
                        SummaryEmbedding.model_version: model_version,
                        SummaryEmbedding.dimensions: dimensions,
                        SummaryEmbedding.language: language,
                        SummaryEmbedding.created_at: dt.datetime.now(UTC),
                    }
                ).where(SummaryEmbedding.summary == summary_id).execute()

        await self._execute(_upsert, operation_name="create_or_update_summary_embedding")

    async def async_get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Retrieve embedding for a summary."""

        def _get() -> dict[str, Any] | None:
            embedding = SummaryEmbedding.get_or_none(SummaryEmbedding.summary == summary_id)
            return model_to_dict(embedding)

        return await self._execute(_get, operation_name="get_summary_embedding", read_only=True)
