"""Factory for creating the configured embedding service.

Backward-compat re-export — real implementation lives in
app.infrastructure.embedding.embedding_factory.
"""

from app.infrastructure.embedding.embedding_factory import create_embedding_service

__all__ = ["create_embedding_service"]
