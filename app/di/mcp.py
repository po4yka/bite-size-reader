from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from app.config import load_config
from app.core.embedding_space import resolve_embedding_space_identifier
from app.di.database import init_read_only_database_proxy
from app.di.types import McpRuntime, McpScope, McpServiceState

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from app.config import AppConfig

CHROMA_RETRY_INTERVAL_SEC = 60.0
LOCAL_VECTOR_RETRY_INTERVAL_SEC = 60.0

logger = logging.getLogger(__name__)


def build_mcp_runtime(
    *,
    db_path: str | None = None,
    user_id: int | None = None,
    cfg: AppConfig | None = None,
) -> McpRuntime:
    """Build the MCP runtime with read-only SQLite binding and lazy service state."""
    path = db_path or os.getenv("DB_PATH", "/data/app.db")
    database = init_read_only_database_proxy(path)
    return McpRuntime(
        cfg=cfg,
        db_path=path,
        database=database,
        scope=McpScope(user_id=user_id),
    )


def set_mcp_user_scope(runtime: McpRuntime, user_id: int | None) -> None:
    runtime.scope.user_id = user_id


async def _init_lazy_service(
    state: McpServiceState,
    creator: Callable[[], Coroutine[Any, Any, Any]],
    retry_interval: float,
    log_event: str,
) -> Any:
    """Generic double-checked-lock helper for lazy service initialization with retry backoff.

    Args:
        state: Mutable state object tracking the service instance and failure timestamps.
        creator: Async callable that builds and returns the service instance.
        retry_interval: Seconds to wait before retrying after a failed init.
        log_event: Structured log event name emitted on init failure.

    Returns:
        The initialized service, or None if init failed or is within the retry backoff window.
    """
    if state.service is not None:
        return state.service

    now = time.monotonic()
    if state.last_failed_at is not None and (now - state.last_failed_at) < retry_interval:
        return None

    if state.init_lock is None:
        state.init_lock = asyncio.Lock()

    async with state.init_lock:
        if state.service is not None:
            return state.service

        now = time.monotonic()
        if state.last_failed_at is not None and (now - state.last_failed_at) < retry_interval:
            return None

        try:
            state.service = await creator()
            state.last_failed_at = None
            return state.service
        except Exception:
            state.last_failed_at = time.monotonic()
            logger.warning(log_event, exc_info=True, extra={"retry_in_sec": retry_interval})
            return None


async def ensure_mcp_chroma_service(runtime: McpRuntime) -> Any:
    """Initialize and cache the MCP Chroma search service with retry backoff."""

    async def _create() -> Any:
        from app.infrastructure.embedding.embedding_factory import create_embedding_service
        from app.infrastructure.search.chroma_vector_search_service import (
            ChromaVectorSearchService,
        )
        from app.infrastructure.vector.chroma_store import ChromaVectorStore

        if runtime.cfg is None:
            runtime.cfg = load_config(allow_stub_telegram=True)
        cfg = runtime.cfg.vector_store
        embedding = create_embedding_service(runtime.cfg.embedding)
        store = ChromaVectorStore(
            host=cfg.host,
            auth_token=cfg.auth_token,
            environment=cfg.environment,
            user_scope=cfg.user_scope,
            collection_version=cfg.collection_version,
            embedding_space=resolve_embedding_space_identifier(runtime.cfg.embedding),
            required=cfg.required,
            connection_timeout=cfg.connection_timeout,
        )
        runtime.chroma_state.resources = (store, embedding)
        return ChromaVectorSearchService(
            vector_store=store,
            embedding_service=embedding,
            default_top_k=100,
        )

    return await _init_lazy_service(
        runtime.chroma_state,
        _create,
        CHROMA_RETRY_INTERVAL_SEC,
        "mcp_chroma_init_failed",
    )


async def ensure_mcp_local_vector_service(runtime: McpRuntime) -> Any:
    """Initialize and cache the local embedding fallback used by MCP tools."""

    async def _create() -> Any:
        from app.infrastructure.embedding.embedding_factory import create_embedding_service

        if runtime.cfg is None:
            runtime.cfg = load_config(allow_stub_telegram=True)
        service = create_embedding_service(runtime.cfg.embedding)
        runtime.local_vector_state.resources = (service,)
        return service

    return await _init_lazy_service(
        runtime.local_vector_state,
        _create,
        LOCAL_VECTOR_RETRY_INTERVAL_SEC,
        "mcp_local_vector_init_failed",
    )


async def close_mcp_runtime(runtime: McpRuntime) -> None:
    """Release lazily-created MCP resources."""
    for state in (runtime.chroma_state, runtime.local_vector_state):
        resources = state.resources
        state.service = None
        state.resources = ()
        for resource in resources:
            close = getattr(resource, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    logger.warning("mcp_resource_close_failed", exc_info=True)
    try:
        runtime.database.close()
    except Exception:
        logger.warning("mcp_database_close_failed", exc_info=True)
