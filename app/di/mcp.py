from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

from app.config import load_config
from app.core.embedding_space import resolve_embedding_space_identifier
from app.di.database import init_read_only_database_proxy
from app.di.types import McpRuntime, McpScope

if TYPE_CHECKING:
    from app.config import AppConfig

CHROMA_RETRY_INTERVAL_SEC = 60.0
LOCAL_VECTOR_RETRY_INTERVAL_SEC = 60.0


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


async def get_mcp_chroma_service(runtime: McpRuntime) -> Any:
    """Initialize and cache the MCP Chroma search service with retry backoff."""
    state = runtime.chroma_state
    if state.service is not None:
        return state.service

    now = time.monotonic()
    if (
        state.last_failed_at is not None
        and (now - state.last_failed_at) < CHROMA_RETRY_INTERVAL_SEC
    ):
        return None

    if state.init_lock is None:
        state.init_lock = asyncio.Lock()

    async with state.init_lock:
        if state.service is not None:
            return state.service

        now = time.monotonic()
        if (
            state.last_failed_at is not None
            and (now - state.last_failed_at) < CHROMA_RETRY_INTERVAL_SEC
        ):
            return None

        try:
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
            state.resources = (store, embedding)
            state.service = ChromaVectorSearchService(
                vector_store=store,
                embedding_service=embedding,
                default_top_k=100,
            )
            state.last_failed_at = None
            return state.service
        except Exception:
            state.last_failed_at = time.monotonic()
            return None


async def get_mcp_local_vector_service(runtime: McpRuntime) -> Any:
    """Initialize and cache the local embedding fallback used by MCP tools."""
    state = runtime.local_vector_state
    if state.service is not None:
        return state.service

    now = time.monotonic()
    if (
        state.last_failed_at is not None
        and (now - state.last_failed_at) < LOCAL_VECTOR_RETRY_INTERVAL_SEC
    ):
        return None

    if state.init_lock is None:
        state.init_lock = asyncio.Lock()

    async with state.init_lock:
        if state.service is not None:
            return state.service
        now = time.monotonic()
        if (
            state.last_failed_at is not None
            and (now - state.last_failed_at) < LOCAL_VECTOR_RETRY_INTERVAL_SEC
        ):
            return None

        try:
            from app.infrastructure.embedding.embedding_factory import create_embedding_service

            if runtime.cfg is None:
                runtime.cfg = load_config(allow_stub_telegram=True)
            state.service = create_embedding_service(runtime.cfg.embedding)
            state.resources = (state.service,)
            state.last_failed_at = None
            return state.service
        except Exception:
            state.last_failed_at = time.monotonic()
            return None


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
                    pass
    try:
        runtime.database.close()
    except Exception:
        pass
