"""Service for semantic search using vector embeddings."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.db.database import Database
    from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VectorSearchResult:
    """Result from vector similarity search."""

    request_id: int
    summary_id: int
    similarity_score: float  # 0.0 to 1.0 (higher = more similar)
    url: str | None
    title: str | None
    snippet: str | None
    source: str | None = None
    published_at: str | None = None


class VectorSearchService:
    """Semantic search using vector embeddings."""

    def __init__(
        self,
        db: Database,
        embedding_service: EmbeddingService,
        *,
        max_results: int = 25,
        min_similarity: float = 0.3,
    ) -> None:
        """Initialize vector search service.

        Args:
            db: Database instance
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

        self._db = db
        self._embedding_service = embedding_service
        self._max_results = max_results
        self._min_similarity = min_similarity

    async def search(
        self,
        query: str,
        *,
        correlation_id: str | None = None,
    ) -> list[VectorSearchResult]:
        """Find articles semantically similar to query.

        Args:
            query: Search query text
            correlation_id: Optional correlation ID for logging

        Returns:
            List of VectorSearchResult sorted by similarity (highest first)
        """
        if not query or not query.strip():
            logger.warning("empty_query_for_vector_search", extra={"cid": correlation_id})
            return []

        # Generate query embedding
        try:
            query_embedding = await self._embedding_service.generate_embedding(query.strip())
        except Exception:
            logger.exception(
                "query_embedding_generation_failed",
                extra={"cid": correlation_id, "query": query[:100]},
            )
            return []

        # Fetch all embeddings from database
        candidates = await self._fetch_all_embeddings()

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
            },
        )

        return filtered[: self._max_results]

    async def _fetch_all_embeddings(self) -> list[dict[str, Any]]:
        """Fetch all embeddings with metadata from database.

        Returns:
            List of dicts with keys: request_id, summary_id, embedding,
                url, title, snippet, source, published_at
        """
        from app.db.models import Request, Summary, SummaryEmbedding

        def _query() -> list[dict[str, Any]]:
            results = []

            with self._db._database.connection_context():
                query = (
                    SummaryEmbedding.select(SummaryEmbedding, Summary, Request)
                    .join(Summary)
                    .join(Request)
                )

                for row in query:
                    try:
                        # Deserialize embedding
                        embedding = self._embedding_service.deserialize_embedding(
                            row.embedding_blob
                        )

                        # Extract metadata from summary payload
                        payload = row.summary.json_payload or {}
                        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

                        # Build URL
                        url = (
                            metadata.get("canonical_url")
                            or metadata.get("url")
                            or row.summary.request.normalized_url
                            or row.summary.request.input_url
                        )

                        # Extract title
                        title = metadata.get("title") or payload.get("title")

                        # Extract snippet
                        snippet = (
                            payload.get("summary_250")
                            or payload.get("tldr")
                            or payload.get("summary_1000")
                        )
                        if snippet and len(snippet) > 300:
                            snippet = snippet[:297] + "..."

                        # Extract source and published date
                        source = metadata.get("domain") or metadata.get("source")
                        published_at = (
                            metadata.get("published_at")
                            or metadata.get("published")
                            or metadata.get("last_updated")
                        )

                        results.append(
                            {
                                "request_id": row.summary.request.id,
                                "summary_id": row.summary.id,
                                "embedding": embedding,
                                "url": url,
                                "title": title or url,
                                "snippet": snippet,
                                "source": source,
                                "published_at": published_at,
                            }
                        )
                    except Exception:
                        logger.exception(
                            "failed_to_process_embedding_row",
                            extra={"summary_id": row.summary.id},
                        )
                        continue

            return results

        return await asyncio.to_thread(_query)

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
            except Exception:
                logger.exception(
                    "similarity_computation_failed",
                    extra={"summary_id": candidate.get("summary_id")},
                )
                continue

        return results
