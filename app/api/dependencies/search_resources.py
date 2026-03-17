"""Chroma search accessors backed by the shared API runtime."""

from __future__ import annotations

from typing import Any

from app.core.logging_utils import get_logger
from app.di.api import ensure_api_runtime, get_current_api_runtime, resolve_api_runtime

logger = get_logger(__name__)


async def get_chroma_search_service(
    request: Any = None,
) -> Any:
    """FastAPI dependency for the shared Chroma search service."""
    runtime = None
    try:
        runtime = resolve_api_runtime(request)
    except RuntimeError:
        runtime = await ensure_api_runtime()

    service = runtime.search.chroma_vector_search_service
    if service is not None:
        return service

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
