"""Backward-compat re-export — real implementation in app/infrastructure/search/hybrid_search_service."""

from app.infrastructure.search.hybrid_search_service import (
    HybridSearchService,
    RerankerProtocol,
)

__all__ = ["HybridSearchService", "RerankerProtocol"]
