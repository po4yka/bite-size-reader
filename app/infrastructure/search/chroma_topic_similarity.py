"""Chroma-backed topic similarity for signal scoring."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.application.services.signal_scoring import SignalCandidate
    from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol
    from app.infrastructure.vector.result_types import VectorQueryResult

logger = get_logger(__name__)


class ChromaQueryStore(Protocol):
    """Subset of the vector store used by signal topic similarity."""

    def query(
        self,
        query_vector: Sequence[float],
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> VectorQueryResult:
        """Query similar vectors."""


class ChromaTopicSimilarityAdapter:
    """Topic similarity adapter backed by the existing Chroma summary collection."""

    def __init__(
        self,
        *,
        vector_store: ChromaQueryStore,
        embedding_service: EmbeddingServiceProtocol,
        user_id: int | None = None,
        top_k: int = 8,
    ) -> None:
        if top_k <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._user_id = user_id
        self._top_k = top_k

    def is_ready(self) -> bool:
        health_check = getattr(self._vector_store, "health_check", None)
        if callable(health_check):
            return bool(health_check())
        return bool(getattr(self._vector_store, "available", False))

    async def score_item(self, candidate: SignalCandidate) -> float:
        query_text = self._candidate_text(candidate)
        if not query_text:
            return 0.0

        try:
            query_embedding = await self._embedding_service.generate_embedding(
                query_text,
                task_type="query",
            )
            filters: dict[str, Any] = {}
            if self._user_id is not None:
                filters["user_id"] = self._user_id
            result = await asyncio.to_thread(
                self._vector_store.query,
                query_embedding,
                filters,
                self._top_k,
            )
        except Exception:
            logger.warning(
                "signal_chroma_similarity_failed",
                extra={"feed_item_id": candidate.feed_item_id},
                exc_info=True,
            )
            return 0.0

        scores = [self._distance_to_similarity(hit.distance) for hit in result.hits]
        return max(scores, default=0.0)

    @staticmethod
    def _candidate_text(candidate: SignalCandidate) -> str:
        metadata_text = candidate.metadata.get("content_text") or candidate.metadata.get("text")
        parts = [
            candidate.title or "",
            str(metadata_text or ""),
            candidate.canonical_url or "",
        ]
        return "\n".join(part.strip() for part in parts if part and part.strip())

    @staticmethod
    def _distance_to_similarity(value: Any) -> float:
        try:
            distance = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, 1.0 - distance))
