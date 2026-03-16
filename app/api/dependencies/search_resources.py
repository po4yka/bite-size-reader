"""Chroma search accessors backed by the shared API runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger
from app.di.api import get_current_api_runtime, get_or_create_api_runtime, resolve_api_runtime

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol

logger = get_logger(__name__)

_test_service: Any | None = None
_test_embedding: EmbeddingServiceProtocol | None = None
_test_vector_store: Any | None = None
_test_embedding_factory: Callable[[], EmbeddingServiceProtocol] | None = None
_test_vector_store_factory: Callable[[Any], Any] | None = None
_test_config_factory: Callable[[], Any] | None = None


async def get_chroma_search_service(
    request: Any = None,
) -> Any:
    """FastAPI dependency for the shared Chroma search service."""
    if (
        request is None
        and _test_embedding_factory
        and _test_vector_store_factory
        and _test_config_factory
    ):
        return await _get_test_service()

    runtime = None
    try:
        runtime = resolve_api_runtime(request)
    except RuntimeError:
        if _test_embedding_factory and _test_vector_store_factory and _test_config_factory:
            return await _get_test_service()
        runtime = await get_or_create_api_runtime()

    service = runtime.search.chroma_vector_search_service
    if service is not None:
        return service

    if _test_embedding_factory and _test_vector_store_factory and _test_config_factory:
        return await _get_test_service()

    msg = "Chroma search service is unavailable"
    raise RuntimeError(msg)


async def shutdown_chroma_search_resources() -> None:
    """Release only API search resources without tearing down the whole runtime."""
    try:
        runtime = get_current_api_runtime()
    except RuntimeError:
        runtime = None

    if runtime is not None:
        if runtime.search.vector_store is not None:
            await runtime.search.vector_store.aclose()
        await runtime.search.embedding_service.aclose()

    await _shutdown_test_service()


def set_chroma_factories_for_tests(
    *,
    embedding_factory: Callable[[], EmbeddingServiceProtocol] | None = None,
    vector_store_factory: Callable[[Any], Any] | None = None,
    config_factory: Callable[[], Any] | None = None,
) -> None:
    """Test helper to provide an isolated Chroma service without app startup."""
    global _test_embedding_factory, _test_vector_store_factory, _test_config_factory
    _test_embedding_factory = embedding_factory
    _test_vector_store_factory = vector_store_factory
    _test_config_factory = config_factory
    if embedding_factory is None and vector_store_factory is None and config_factory is None:
        _reset_test_service()


async def _get_test_service() -> Any:
    global _test_service, _test_embedding, _test_vector_store
    if _test_service is not None:
        return _test_service

    config = _test_config_factory()
    _test_embedding = _test_embedding_factory()
    _test_vector_store = _test_vector_store_factory(config)
    from app.infrastructure.search.chroma_vector_search_service import ChromaVectorSearchService

    _test_service = ChromaVectorSearchService(
        vector_store=_test_vector_store,
        embedding_service=_test_embedding,
        default_top_k=25,
    )
    logger.info("chroma_search_service_initialized", extra={"host": getattr(config, "host", None)})
    return _test_service


async def _shutdown_test_service() -> None:
    if _test_vector_store is not None:
        await _test_vector_store.aclose()
    if _test_embedding is not None:
        await _test_embedding.aclose()
    _reset_test_service()


def _reset_test_service() -> None:
    global _test_service, _test_embedding, _test_vector_store
    _test_service = None
    _test_embedding = None
    _test_vector_store = None
