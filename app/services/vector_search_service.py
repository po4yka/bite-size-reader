"""Backward-compat re-export — real implementation in app/infrastructure/search/vector_search_service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)
from app.infrastructure.search.vector_search_service import (
    VectorSearchResult,
    VectorSearchService as _CanonicalVectorSearch,
)

if TYPE_CHECKING:
    from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol


class VectorSearchService(_CanonicalVectorSearch):
    """Backward-compat wrapper that accepts a DatabaseSessionManager instead of ports."""

    def __init__(
        self,
        db: Any,
        *,
        embedding_service: EmbeddingServiceProtocol,
        max_results: int = 25,
        min_similarity: float = 0.3,
        candidate_multiplier: int = 40,
        fallback_scan_limit: int = 5000,
    ) -> None:
        super().__init__(
            embedding_repository=SqliteEmbeddingRepositoryAdapter(db),
            topic_search_repository=SqliteTopicSearchRepositoryAdapter(db),
            embedding_service=embedding_service,
            max_results=max_results,
            min_similarity=min_similarity,
            candidate_multiplier=candidate_multiplier,
            fallback_scan_limit=fallback_scan_limit,
        )


__all__ = ["VectorSearchResult", "VectorSearchService"]
