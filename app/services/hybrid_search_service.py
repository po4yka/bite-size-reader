"""Service for hybrid search combining full-text and vector search."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Protocol

from app.services.topic_search import TopicArticle

if TYPE_CHECKING:
    from app.services.chroma_vector_search_service import (
        ChromaVectorSearchResult,
    )
    from app.services.query_expansion_service import QueryExpansionService
    from app.services.search_filters import SearchFilters
    from app.services.topic_search import LocalTopicSearchService


class RerankerProtocol(Protocol):
    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        text_field: str = ...,
        title_field: str = ...,
        id_field: str | None = ...,
        score_field: str = ...,
    ) -> list[dict[str, Any]]: ...


logger = logging.getLogger(__name__)


class HybridSearchService:
    """Combines full-text (FTS5) and vector (semantic) search."""

    def __init__(
        self,
        fts_service: LocalTopicSearchService,
        vector_service: Any,
        *,
        fts_weight: float = 0.4,
        vector_weight: float = 0.6,
        max_results: int = 25,
        query_expansion: QueryExpansionService | None = None,
        reranking: RerankerProtocol | None = None,
    ) -> None:
        """Initialize hybrid search service.

        Args:
            fts_service: Full-text search service (FTS5)
            vector_service: Vector similarity search service
            fts_weight: Weight for FTS scores (0.0-1.0)
            vector_weight: Weight for vector scores (0.0-1.0)
            max_results: Maximum number of results to return
            query_expansion: Optional query expansion service for FTS
            reranking: Optional cross-encoder re-ranking service
        """
        if not 0.0 <= fts_weight <= 1.0:
            msg = "fts_weight must be between 0.0 and 1.0"
            raise ValueError(msg)
        if not 0.0 <= vector_weight <= 1.0:
            msg = "vector_weight must be between 0.0 and 1.0"
            raise ValueError(msg)
        if max_results <= 0:
            msg = "max_results must be positive"
            raise ValueError(msg)

        self._fts = fts_service
        self._vector = vector_service
        self._fts_weight = fts_weight
        self._vector_weight = vector_weight
        self._max_results = max_results
        self._query_expansion = query_expansion
        self._reranking = reranking

    async def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        correlation_id: str | None = None,
    ) -> list[TopicArticle]:
        """Hybrid search combining keyword matching and semantic similarity.

        Args:
            query: Search query text
            filters: Optional search filters (date, source, language)
            correlation_id: Optional correlation ID for logging

        Returns:
            List of TopicArticle sorted by combined score (highest first)
        """
        if not query or not query.strip():
            logger.warning("empty_query_for_hybrid_search", extra={"cid": correlation_id})
            return []

        # Optionally expand query for FTS (improves keyword matching)
        fts_query = query.strip()
        if self._query_expansion:
            expanded = self._query_expansion.expand_for_fts(fts_query)
            logger.debug(
                "query_expanded_for_fts",
                extra={"cid": correlation_id, "original": fts_query, "expanded": expanded},
            )
            fts_query = expanded

        # Run both searches in parallel
        # FTS uses expanded query, vector uses original (semantic search handles variations)
        fts_task = asyncio.create_task(
            self._fts.find_articles(fts_query, correlation_id=correlation_id)
        )
        vector_task = asyncio.create_task(
            self._vector.search(
                query.strip(),
                language=getattr(filters, "language", None) if filters else None,
                user_scope=getattr(self._vector, "user_scope", None),
                correlation_id=correlation_id,
            )
        )

        fts_results, vector_search_results = await asyncio.gather(fts_task, vector_task)
        vector_results: list[ChromaVectorSearchResult] = vector_search_results.results

        # Apply filters to FTS results (vector results already filtered)
        if filters and filters.has_filters():
            fts_results = [r for r in fts_results if filters.matches(r)]

        # Combine and rank results
        combined = self._combine_results(fts_results, vector_results)

        # Sort by combined score (highest first)
        combined.sort(key=lambda x: x["combined_score"], reverse=True)

        # Optionally re-rank top results with cross-encoder
        if self._reranking:
            # Re-rank top candidates for better precision
            top_candidates = combined[: self._max_results * 2]  # Re-rank 2x max for better quality
            if top_candidates:
                reranked = await self._reranking.rerank(
                    query=query.strip(),
                    results=top_candidates,
                    text_field="text",
                    title_field="title",
                )
                # Use re-ranked results, fall back to combined if re-ranking fails
                combined = reranked if reranked else combined

        # Convert to TopicArticle format
        articles = [
            TopicArticle(
                title=r["title"],
                url=r["url"],
                snippet=r["snippet"],
                source=r.get("source"),
                published_at=r.get("published_at"),
            )
            for r in combined[: self._max_results]
        ]

        logger.info(
            "hybrid_search_completed",
            extra={
                "cid": correlation_id,
                "query_length": len(query),
                "fts_results": len(fts_results),
                "vector_results": len(vector_results),
                "combined_unique": len(combined),
                "returned_results": len(articles),
                "reranking_used": bool(self._reranking),
                "filters": str(filters) if filters else "none",
            },
        )

        return articles

    def _combine_results(
        self,
        fts_results: list[TopicArticle],
        vector_results: list[ChromaVectorSearchResult],
    ) -> list[dict]:
        """Combine and normalize scores from both search methods.

        Args:
            fts_results: Results from full-text search
            vector_results: Results from vector search

        Returns:
            List of dicts with combined scores and metadata
        """
        # Normalize FTS scores using rank-based scoring
        # (BM25 scores are unbounded, so we use position-based normalization)
        fts_scores: dict[str, float] = {}
        for idx, result in enumerate(fts_results):
            score = 1.0 - (idx / max(len(fts_results), 1))
            fts_scores[result.url] = score

        vector_scores: dict[str, float] = {}
        vector_data: dict[str, ChromaVectorSearchResult] = {}
        for vector_result in vector_results:
            result_id = (
                getattr(vector_result, "window_id", None)
                or getattr(vector_result, "chunk_id", None)
                or vector_result.url
            )
            if result_id:
                vector_scores[result_id] = getattr(vector_result, "similarity_score", 0.0)
                vector_data[result_id] = vector_result

        all_ids = set(vector_scores.keys()) | set(fts_scores.keys())
        combined = []

        for result_id in all_ids:
            vector_match = vector_data.get(result_id)

            url = (
                getattr(vector_match, "url", None)
                if vector_match
                else next((r.url for r in fts_results if r.url and r.url == result_id), None)
            )
            title = getattr(vector_match, "title", None) if vector_match else None
            snippet = getattr(vector_match, "snippet", None) if vector_match else None
            text = getattr(vector_match, "text", None) if vector_match else None
            source = getattr(vector_match, "source", None) if vector_match else None
            published_at = getattr(vector_match, "published_at", None) if vector_match else None

            fts_score = fts_scores.get(url or result_id, 0.0)
            vector_score = vector_scores.get(result_id, 0.0)
            combined_score = self._fts_weight * fts_score + self._vector_weight * vector_score

            combined.append(
                {
                    "id": result_id,
                    "url": url or result_id,
                    "title": title or (url or result_id),
                    "snippet": snippet or text,
                    "text": text or snippet,
                    "source": source,
                    "published_at": published_at,
                    "combined_score": combined_score,
                    "fts_score": fts_score,
                    "vector_score": vector_score,
                    "window_id": getattr(vector_match, "window_id", None) if vector_match else None,
                    "window_index": getattr(vector_match, "window_index", None)
                    if vector_match
                    else None,
                    "chunk_id": getattr(vector_match, "chunk_id", None) if vector_match else None,
                    "neighbor_chunk_ids": getattr(vector_match, "neighbor_chunk_ids", [])
                    if vector_match
                    else [],
                }
            )

        return combined
