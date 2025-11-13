"""Service for hybrid search combining full-text and vector search."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.topic_search import TopicArticle

if TYPE_CHECKING:
    from app.services.topic_search import LocalTopicSearchService
    from app.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


class HybridSearchService:
    """Combines full-text (FTS5) and vector (semantic) search."""

    def __init__(
        self,
        fts_service: LocalTopicSearchService,
        vector_service: VectorSearchService,
        *,
        fts_weight: float = 0.4,
        vector_weight: float = 0.6,
        max_results: int = 25,
    ) -> None:
        """Initialize hybrid search service.

        Args:
            fts_service: Full-text search service (FTS5)
            vector_service: Vector similarity search service
            fts_weight: Weight for FTS scores (0.0-1.0)
            vector_weight: Weight for vector scores (0.0-1.0)
            max_results: Maximum number of results to return
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

    async def search(
        self,
        query: str,
        *,
        correlation_id: str | None = None,
    ) -> list[TopicArticle]:
        """Hybrid search combining keyword matching and semantic similarity.

        Args:
            query: Search query text
            correlation_id: Optional correlation ID for logging

        Returns:
            List of TopicArticle sorted by combined score (highest first)
        """
        if not query or not query.strip():
            logger.warning("empty_query_for_hybrid_search", extra={"cid": correlation_id})
            return []

        # Run both searches in parallel
        fts_task = asyncio.create_task(
            self._fts.find_articles(query.strip(), correlation_id=correlation_id)
        )
        vector_task = asyncio.create_task(
            self._vector.search(query.strip(), correlation_id=correlation_id)
        )

        fts_results, vector_results = await asyncio.gather(fts_task, vector_task)

        # Combine and rank results
        combined = self._combine_results(fts_results, vector_results)

        # Sort by combined score (highest first)
        combined.sort(key=lambda x: x["combined_score"], reverse=True)

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
            },
        )

        return articles

    def _combine_results(
        self,
        fts_results: list[TopicArticle],
        vector_results: list,
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
        fts_scores = {}
        for idx, result in enumerate(fts_results):
            # Rank-based score: 1.0 for top result, decreasing linearly
            score = 1.0 - (idx / max(len(fts_results), 1))
            fts_scores[result.url] = score

        # Vector scores are already normalized (0-1 cosine similarity)
        vector_scores = {}
        vector_data = {}
        for result in vector_results:
            vector_scores[result.url] = result.similarity_score
            vector_data[result.url] = result

        # Combine all URLs from both sources
        all_urls = set(fts_scores.keys()) | set(vector_scores.keys())
        combined = []

        for url in all_urls:
            fts_score = fts_scores.get(url, 0.0)
            vector_score = vector_scores.get(url, 0.0)

            # Weighted combination
            combined_score = self._fts_weight * fts_score + self._vector_weight * vector_score

            # Get metadata (prefer FTS source if available, fallback to vector)
            fts_match = next((r for r in fts_results if r.url == url), None)
            vector_match = vector_data.get(url)

            if fts_match:
                title = fts_match.title
                snippet = fts_match.snippet
                source = fts_match.source
                published_at = fts_match.published_at
            elif vector_match:
                title = vector_match.title
                snippet = vector_match.snippet
                source = vector_match.source
                published_at = vector_match.published_at
            else:
                # This shouldn't happen, but handle it gracefully
                title = url
                snippet = None
                source = None
                published_at = None

            combined.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "source": source,
                    "published_at": published_at,
                    "combined_score": combined_score,
                    "fts_score": fts_score,
                    "vector_score": vector_score,
                }
            )

        return combined
