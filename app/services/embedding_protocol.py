"""Protocol definition for embedding service providers.

Backward-compat re-export — real implementation lives in
app.infrastructure.embedding.embedding_protocol.
"""

from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol

__all__ = ["EmbeddingServiceProtocol"]
