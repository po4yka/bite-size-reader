"""Embedding service backed by Google Gemini Embedding 2 API.

Backward-compat re-export — real implementation lives in
app.infrastructure.embedding.gemini_embedding_service.
"""

from app.infrastructure.embedding.gemini_embedding_service import GeminiEmbeddingService

__all__ = ["GeminiEmbeddingService"]
