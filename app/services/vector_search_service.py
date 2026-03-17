"""Service for semantic search using vector embeddings."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.lang import detect_language
from app.infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager
    from app.services.embedding_protocol import EmbeddingServiceProtocol
    from app.services.search_filters import SearchFilters

logger = logging.getLogger(__name__)


class VectorSearchResult(BaseModel):
    """Result from vector similarity search."""

    model_config = ConfigDict(frozen=True)

    request_id: int
    summary_id: int
    similarity_score: float = Field(ge=0.0, le=1.0)  # 0.0 to 1.0 (higher = more similar)
    url: str | None
    title: str | None
    snippet: str | None
    source: str | None = None
    published_at: str | None = None


class VectorSearchService:
    """Semantic search using vector embeddings."""

    def __init__(
        self,
        db: DatabaseSessionManager | Any,
        embedding_service: EmbeddingServiceProtocol,
        *,
        max_results: int = 25,
        min_similarity: float = 0.3,
        candidate_multiplier: int = 40,
        fallback_scan_limit: int = 5000,
    ) -> None:
        """Initialize vector search service.

        Args:
            db: DatabaseSessionManager instance or session
            embedding_service: Service for generating embeddings
            max_results: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0.0-1.0)
        """
        if max_results <= 0:
            msg = "max_results must be positive"
            raise ValueError(msg)
        if not 0.0 <= min_similarity <= 1.0:
            msg = "min_similarity must be between 0.0 and 1.0"
            raise ValueError(msg)
        if candidate_multiplier <= 0:
            msg = "candidate_multiplier must be positive"
            raise ValueError(msg)
        if fallback_scan_limit <= 0:
            msg = "fallback_scan_limit must be positive"
            raise ValueError(msg)

        self._db = db
        self._repo = SqliteEmbeddingRepositoryAdapter(db)
        self._topic_repo = SqliteTopicSearchRepositoryAdapter(db)
        self._embedding_service = embedding_service
        self._max_results = max_results
        self._min_similarity = min_similarity
        self._candidate_multiplier = candidate_multiplier
        self._fallback_scan_limit = fallback_scan_limit

    async def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        correlation_id: str | None = None,
    ) -> list[VectorSearchResult]:
        """Find articles semantically similar to query.

        Args:
            query: Search query text
            filters: Optional search filters (date, source, language)
            correlation_id: Optional correlation ID for logging

        Returns:
            List of VectorSearchResult sorted by similarity (highest first)
        """
        if not query or not query.strip():
            logger.warning("empty_query_for_vector_search", extra={"cid": correlation_id})
            return []

        # Detect query language for optimal model selection
        query_language = detect_language(query)

        # Generate query embedding with language-specific model
        try:
            query_embedding = await self._embedding_service.generate_embedding(
                query.strip(), language=query_language, task_type="query"
            )
        except (RuntimeError, ValueError, OSError):
            logger.exception(
                "query_embedding_generation_failed",
                extra={"cid": correlation_id, "query": query[:100], "language": query_language},
            )
            return []

        # Two-stage retrieval:
        # 1) Try topic-index prefilter to get a smaller request-id candidate set.
        # 2) If unavailable, use bounded recent embeddings as a safe fallback.
        candidate_limit = max(self._max_results * self._candidate_multiplier, self._max_results)
        candidate_request_ids = await self._topic_repo.async_search_request_ids(
            query,
            candidate_limit=candidate_limit,
        )

        if candidate_request_ids:
            candidates = await self._fetch_embeddings_by_request_ids(candidate_request_ids)
        else:
            candidates = await self._fetch_recent_embeddings(limit=self._fallback_scan_limit)

        if not candidates:
            logger.warning("no_embeddings_available", extra={"cid": correlation_id})
            return []

        # Compute similarities
        results = await asyncio.to_thread(
            self._compute_similarities,
            query_embedding,
            candidates,
        )

        # Filter by minimum similarity
        filtered = [r for r in results if r.similarity_score >= self._min_similarity]

        # Apply search filters
        if filters and filters.has_filters():
            filtered = [r for r in filtered if filters.matches(r)]

        # Sort by similarity (highest first)
        filtered.sort(key=lambda x: x.similarity_score, reverse=True)

        logger.info(
            "vector_search_completed",
            extra={
                "cid": correlation_id,
                "query_length": len(query),
                "total_candidates": len(candidates),
                "filtered_results": len(filtered),
                "returned_results": min(len(filtered), self._max_results),
                "filters": str(filters) if filters else "none",
            },
        )

        return filtered[: self._max_results]

    async def _fetch_embeddings_by_request_ids(
        self,
        request_ids: list[int],
    ) -> list[dict[str, Any]]:
        """Fetch scoped embeddings with metadata from database.

        Returns:
            List of dicts with keys: request_id, summary_id, embedding,
                url, title, snippet, source, published_at
        """
        rows = await self._repo.async_get_embeddings_by_request_ids(request_ids)
        return self._materialize_candidates(rows)

    async def _fetch_recent_embeddings(self, *, limit: int) -> list[dict[str, Any]]:
        """Fetch bounded recent embeddings with metadata from database.

        Returns:
            List of dicts with keys: request_id, summary_id, embedding,
                url, title, snippet, source, published_at
        """
        rows = await self._repo.async_get_recent_embeddings(limit=limit)

        return self._materialize_candidates(rows)

    def _materialize_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deserialize embeddings and normalize metadata for similarity matching."""
        results = []

        for row in rows:
            try:
                embedding = self._embedding_service.deserialize_embedding(row["embedding_blob"])

                payload = row["json_payload"] or {}
                metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

                url = (
                    metadata.get("canonical_url")
                    or metadata.get("url")
                    or row.get("normalized_url")
                    or row.get("input_url")
                )

                title = metadata.get("title") or payload.get("title")

                snippet = (
                    payload.get("summary_250") or payload.get("tldr") or payload.get("summary_1000")
                )
                if snippet and len(snippet) > 300:
                    snippet = snippet[:297] + "..."

                source = metadata.get("domain") or metadata.get("source")
                published_at = (
                    metadata.get("published_at")
                    or metadata.get("published")
                    or metadata.get("last_updated")
                )

                results.append(
                    {
                        "request_id": row["request_id"],
                        "summary_id": row["summary_id"],
                        "embedding": embedding,
                        "url": url,
                        "title": title or url,
                        "snippet": snippet,
                        "source": source,
                        "published_at": published_at,
                    }
                )
            except (ValueError, KeyError, AttributeError, TypeError):
                logger.exception(
                    "failed_to_process_embedding_row",
                    extra={"summary_id": row.get("summary_id")},
                )
                continue

        return results

    def _compute_similarities(
        self,
        query_embedding: Any,
        candidates: list[dict[str, Any]],
    ) -> list[VectorSearchResult]:
        """Compute cosine similarity for all candidates.

        Args:
            query_embedding: Query embedding vector
            candidates: List of candidate dicts with 'embedding' key

        Returns:
            List of VectorSearchResult with similarity scores
        """
        from scipy.spatial.distance import cosine

        results = []

        for candidate in candidates:
            try:
                candidate_embedding = candidate["embedding"]

                # Compute cosine similarity
                # cosine() returns distance, so we convert to similarity
                distance = cosine(query_embedding, candidate_embedding)
                similarity = 1.0 - distance

                results.append(
                    VectorSearchResult(
                        request_id=candidate["request_id"],
                        summary_id=candidate["summary_id"],
                        similarity_score=float(similarity),
                        url=candidate["url"],
                        title=candidate["title"],
                        snippet=candidate["snippet"],
                        source=candidate.get("source"),
                        published_at=candidate.get("published_at"),
                    )
                )
            except (ValueError, TypeError, KeyError):
                logger.exception(
                    "similarity_computation_failed",
                    extra={"summary_id": candidate.get("summary_id")},
                )
                continue

        return results
