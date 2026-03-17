"""Test helpers for Chroma search dependency injection.

Use FastAPI's dependency_overrides for most tests. This module provides a
factory-based helper for tests that need to exercise the Chroma initialization
path itself (e.g. singleton caching, lifecycle management).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol

_test_service: Any | None = None
_test_embedding: EmbeddingServiceProtocol | None = None
_test_vector_store: Any | None = None
_test_embedding_factory: Callable[[], EmbeddingServiceProtocol] | None = None
_test_vector_store_factory: Callable[[Any], Any] | None = None
_test_config_factory: Callable[[], Any] | None = None


def set_chroma_factories(
    *,
    embedding_factory: Callable[[], EmbeddingServiceProtocol] | None = None,
    vector_store_factory: Callable[[Any], Any] | None = None,
    config_factory: Callable[[], Any] | None = None,
) -> None:
    """Configure factory callables used by get_test_chroma_service.

    Call with no arguments (or all-None) to clear the factories and reset state.
    """
    global _test_embedding_factory, _test_vector_store_factory, _test_config_factory
    _test_embedding_factory = embedding_factory
    _test_vector_store_factory = vector_store_factory
    _test_config_factory = config_factory
    if embedding_factory is None and vector_store_factory is None and config_factory is None:
        reset_test_service()


async def get_test_chroma_service() -> Any:
    """Build (and cache) a Chroma search service from the registered factories."""
    global _test_service, _test_embedding, _test_vector_store
    if _test_service is not None:
        return _test_service

    if not (_test_embedding_factory and _test_vector_store_factory and _test_config_factory):
        msg = "Call set_chroma_factories() before get_test_chroma_service()"
        raise RuntimeError(msg)

    config = _test_config_factory()
    _test_embedding = _test_embedding_factory()
    _test_vector_store = _test_vector_store_factory(config)

    from app.infrastructure.search.chroma_vector_search_service import ChromaVectorSearchService

    _test_service = ChromaVectorSearchService(
        vector_store=_test_vector_store,
        embedding_service=_test_embedding,
        default_top_k=25,
    )
    return _test_service


async def shutdown_test_chroma_service() -> None:
    """Release resources created by get_test_chroma_service."""
    if _test_vector_store is not None:
        await _test_vector_store.aclose()
    if _test_embedding is not None:
        await _test_embedding.aclose()
    reset_test_service()


def reset_test_service() -> None:
    """Reset all cached test state."""
    global _test_service, _test_embedding, _test_vector_store
    _test_service = None
    _test_embedding = None
    _test_vector_store = None
