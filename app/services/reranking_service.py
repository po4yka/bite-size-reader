"""Service for re-ranking search results using cross-encoder models."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class RerankingService:
    """Re-ranks search results using cross-encoder for improved relevance."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        *,
        top_k: int | None = None,
    ) -> None:
        """Initialize re-ranking service.

        Args:
            model_name: Name of cross-encoder model to use
                       Default: cross-encoder/ms-marco-MiniLM-L-6-v2 (fast, good quality)
                       Alternative: cross-encoder/ms-marco-MiniLM-L-12-v2 (slower, better)
            top_k: Number of top results to re-rank (None = re-rank all)
                   Recommended: 20-50 for good performance
        """
        self._model_name = model_name
        self._top_k = top_k
        self._model: CrossEncoder | None = None

    def _ensure_model(self) -> CrossEncoder:
        """Lazy load the cross-encoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name, max_length=512)
            logger.info(
                "reranking_model_loaded",
                extra={"model": self._model_name},
            )
        return self._model

    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        text_field: str = "snippet",
        title_field: str = "title",
        score_field: str = "rerank_score",
    ) -> list[dict[str, Any]]:
        """Re-rank results using cross-encoder.

        Args:
            query: Search query
            results: List of result dictionaries
            text_field: Field name containing result text for scoring
            title_field: Field name containing result title
            score_field: Field name to store re-ranking score

        Returns:
            Re-ranked results with score_field added, sorted by relevance
        """
        if not query or not results:
            return results

        # Determine how many to re-rank
        num_to_rerank = len(results) if self._top_k is None else min(self._top_k, len(results))

        if num_to_rerank == 0:
            return results

        # Prepare query-document pairs for scoring
        pairs = []
        for result in results[:num_to_rerank]:
            # Combine title and snippet for better scoring
            title = result.get(title_field, "")
            text = result.get(text_field, "")

            # Create document text (title gets more weight by being first)
            doc_text = f"{title}. {text}".strip() if title else text

            pairs.append([query, doc_text])

        # Score all pairs
        try:
            scores = await self._score_pairs(pairs)
        except Exception:
            logger.exception(
                "reranking_failed",
                extra={"query": query[:100], "num_results": num_to_rerank},
            )
            # Return original results if re-ranking fails
            return results

        # Add scores to results
        reranked = []
        for i, result in enumerate(results[:num_to_rerank]):
            result_copy = result.copy()
            result_copy[score_field] = float(scores[i])
            reranked.append(result_copy)

        # Sort by re-ranking score (highest first)
        reranked.sort(key=lambda x: x[score_field], reverse=True)

        # Append any results that weren't re-ranked
        if num_to_rerank < len(results):
            reranked.extend(results[num_to_rerank:])

        logger.info(
            "reranking_completed",
            extra={
                "query_length": len(query),
                "total_results": len(results),
                "reranked": num_to_rerank,
            },
        )

        return reranked

    async def _score_pairs(self, pairs: list[list[str]]) -> Any:
        """Score query-document pairs using cross-encoder.

        Args:
            pairs: List of [query, document] pairs

        Returns:
            Numpy array of relevance scores
        """
        model = self._ensure_model()

        # Run in thread pool to avoid blocking
        return await asyncio.to_thread(model.predict, pairs, show_progress_bar=False)

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name
