"""Factory for creating the configured embedding service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config.integrations import EmbeddingConfig
    from app.services.embedding_protocol import EmbeddingServiceProtocol


def create_embedding_service(
    config: EmbeddingConfig | None = None,
) -> EmbeddingServiceProtocol:
    """Return an embedding service matching the given configuration.

    When *config* is ``None`` or ``provider == "local"``, the default
    sentence-transformers ``EmbeddingService`` is returned.
    """
    from app.services.embedding_service import EmbeddingService

    if config is None or config.provider == "local":
        return EmbeddingService()

    if config.provider == "gemini":
        from app.services.gemini_embedding_service import GeminiEmbeddingService

        return GeminiEmbeddingService(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
            dimensions=config.gemini_dimensions,
        )

    msg = f"Unknown embedding provider: {config.provider}"
    raise ValueError(msg)
