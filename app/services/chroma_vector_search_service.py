"""Semantic search service backed by Chroma vector store.

Backward-compat re-export -- real implementation lives in
app.infrastructure.search.chroma_vector_search_service.
"""

from app.infrastructure.search.chroma_vector_search_service import (
    ChromaVectorSearchResult,
    ChromaVectorSearchResults,
    ChromaVectorSearchService,
)

__all__ = [
    "ChromaVectorSearchResult",
    "ChromaVectorSearchResults",
    "ChromaVectorSearchService",
]
