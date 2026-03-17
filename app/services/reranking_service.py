"""Service for re-ranking search results using cross-encoder models.

Backward-compat re-export -- real implementation lives in
app.infrastructure.search.reranking_service.
"""

from app.infrastructure.search.reranking_service import (
    OpenRouterRerankingService,
    RerankingService,
)

__all__ = [
    "OpenRouterRerankingService",
    "RerankingService",
]
