"""Chroma search dependency management with explicit lifecycle."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.config import ChromaConfig, load_config
from app.core.logging_utils import get_logger
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.chroma_vector_search_service import ChromaVectorSearchService
from app.services.embedding_service import EmbeddingService

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


def _default_embedding_factory() -> EmbeddingService:
    return EmbeddingService()


def _default_vector_store_factory(config: ChromaConfig) -> ChromaVectorStore:
    return ChromaVectorStore(
        host=config.host,
        auth_token=config.auth_token,
        environment=config.environment,
        user_scope=config.user_scope,
        collection_version=config.collection_version,
    )


def _default_config_factory() -> ChromaConfig:
    return load_config(allow_stub_telegram=True).vector_store


class _ChromaSearchResourceManager:
    _lock = asyncio.Lock()
    _service: ChromaVectorSearchService | None = None
    _vector_store: ChromaVectorStore | None = None
    _embedding: EmbeddingService | None = None
    _embedding_factory: Callable[[], EmbeddingService] = _default_embedding_factory
    _vector_store_factory: Callable[[ChromaConfig], ChromaVectorStore] = (
        _default_vector_store_factory
    )
    _config_factory: Callable[[], ChromaConfig] = _default_config_factory

    @classmethod
    async def get_service(cls) -> ChromaVectorSearchService:
        if cls._service:
            return cls._service

        async with cls._lock:
            if cls._service:
                return cls._service

            config = cls._config_factory()
            embedding = cls._embedding_factory()
            vector_store = cls._vector_store_factory(config)

            cls._embedding = embedding
            cls._vector_store = vector_store
            cls._service = ChromaVectorSearchService(
                vector_store=vector_store,
                embedding_service=embedding,
                default_top_k=25,
            )

            logger.info(
                "chroma_search_service_initialized",
                extra={
                    "host": config.host,
                    "environment": config.environment,
                    "collection_version": config.collection_version,
                },
            )

            return cls._service

    @classmethod
    async def shutdown(cls) -> None:
        async with cls._lock:
            service = cls._service
            embedding = cls._embedding
            vector_store = cls._vector_store

            cls._service = None
            cls._embedding = None
            cls._vector_store = None

        if vector_store:
            try:
                await vector_store.aclose()
            except Exception:  # pragma: no cover - defensive shutdown
                logger.exception("chroma_vector_store_shutdown_failed")

        if embedding:
            try:
                await embedding.aclose()
            except Exception:  # pragma: no cover - defensive shutdown
                logger.exception("embedding_service_shutdown_failed")

        if service:
            logger.info("chroma_search_service_shutdown")

    @classmethod
    def set_factories_for_tests(
        cls,
        *,
        embedding_factory: Callable[[], EmbeddingService] | None = None,
        vector_store_factory: Callable[[ChromaConfig], ChromaVectorStore] | None = None,
        config_factory: Callable[[], ChromaConfig] | None = None,
    ) -> None:
        """Override factories for tests and reset cached instances."""
        cls._embedding_factory = embedding_factory or _default_embedding_factory
        cls._vector_store_factory = vector_store_factory or _default_vector_store_factory
        cls._config_factory = config_factory or _default_config_factory
        cls._service = None
        cls._embedding = None
        cls._vector_store = None


async def get_chroma_search_service() -> ChromaVectorSearchService:
    """FastAPI dependency for a singleton Chroma search service."""
    return await _ChromaSearchResourceManager.get_service()


async def shutdown_chroma_search_resources() -> None:
    """Shutdown hook to release Chroma search resources."""
    await _ChromaSearchResourceManager.shutdown()


def set_chroma_factories_for_tests(
    *,
    embedding_factory: Callable[[], EmbeddingService] | None = None,
    vector_store_factory: Callable[[ChromaConfig], ChromaVectorStore] | None = None,
    config_factory: Callable[[], ChromaConfig] | None = None,
) -> None:
    """Test helper to override factories."""
    _ChromaSearchResourceManager.set_factories_for_tests(
        embedding_factory=embedding_factory,
        vector_store_factory=vector_store_factory,
        config_factory=config_factory,
    )
