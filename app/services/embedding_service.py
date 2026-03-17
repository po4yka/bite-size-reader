"""Service for generating and managing semantic embeddings for articles.

Backward-compat re-export — real implementation lives in
app.infrastructure.embedding.embedding_service.
"""

from app.infrastructure.embedding.embedding_service import (
    EmbeddingService,
    prepare_text_for_embedding,
)

__all__ = ["EmbeddingService", "prepare_text_for_embedding"]
