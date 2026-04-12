from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import app.di.mcp as mcp_di

if TYPE_CHECKING:
    from collections.abc import Iterator

_NO_REQUEST_USER_SCOPE = object()


class McpServerContext:
    """Owns MCP runtime state, user scope, and lazy semantic-search services."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        user_id: int | None = None,
        logger: logging.Logger | None = None,
        chroma_retry_interval_sec: float | None = None,
        local_vector_retry_interval_sec: float | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger("bsr.mcp")
        self.db_path = db_path or os.getenv("DB_PATH", "/data/app.db")
        self._runtime: Any = None
        self._api_runtime: Any = None
        self._user_id = user_id
        self._request_user_id: contextvars.ContextVar[int | None | object] = contextvars.ContextVar(
            "mcp_request_user_id",
            default=_NO_REQUEST_USER_SCOPE,
        )
        self._api_runtime_lock: asyncio.Lock | None = None
        self._chroma_retry_interval_sec = (
            chroma_retry_interval_sec
            if chroma_retry_interval_sec is not None
            else mcp_di.CHROMA_RETRY_INTERVAL_SEC
        )
        self._local_vector_retry_interval_sec = (
            local_vector_retry_interval_sec
            if local_vector_retry_interval_sec is not None
            else mcp_di.LOCAL_VECTOR_RETRY_INTERVAL_SEC
        )

    @property
    def user_id(self) -> int | None:
        request_user_id = self._request_user_id.get()
        if request_user_id is not _NO_REQUEST_USER_SCOPE:
            return cast("int | None", request_user_id)
        return self._runtime.scope.user_id if self._runtime is not None else self._user_id

    @property
    def runtime(self) -> Any | None:
        return self._runtime

    @property
    def api_runtime(self) -> Any | None:
        return self._api_runtime

    @property
    def chroma_last_failed_at(self) -> float | None:
        if self._runtime is None:
            return None
        return self._runtime.chroma_state.last_failed_at

    @property
    def local_vector_last_failed_at(self) -> float | None:
        if self._runtime is None:
            return None
        return self._runtime.local_vector_state.last_failed_at

    def init_runtime(self, db_path: str | None = None) -> Any:
        """Initialize the read-only MCP runtime immediately."""
        if db_path:
            self.db_path = db_path
        mcp_di.CHROMA_RETRY_INTERVAL_SEC = self._chroma_retry_interval_sec
        mcp_di.LOCAL_VECTOR_RETRY_INTERVAL_SEC = self._local_vector_retry_interval_sec
        # Request-scoped overrides are transient and must not leak into the shared runtime.
        self._runtime = mcp_di.build_mcp_runtime(db_path=self.db_path, user_id=self._user_id)
        self.logger.info("Database connected (read-only): %s", self._runtime.db_path)
        return self._runtime

    def ensure_runtime(self, db_path: str | None = None) -> Any:
        if self._runtime is None or (db_path is not None and db_path != self.db_path):
            return self.init_runtime(db_path)
        return self._runtime

    def set_user_scope(self, user_id: int | None) -> None:
        self._user_id = user_id
        if self._runtime is not None:
            mcp_di.set_mcp_user_scope(self._runtime, user_id)

    def set_request_user_scope(self, user_id: int | None) -> contextvars.Token[Any]:
        return self._request_user_id.set(user_id)

    def reset_request_user_scope(self, token: contextvars.Token[Any]) -> None:
        self._request_user_id.reset(token)

    @contextlib.contextmanager
    def request_user_scope(self, user_id: int | None) -> Iterator[None]:
        token = self.set_request_user_scope(user_id)
        try:
            yield
        finally:
            self.reset_request_user_scope(token)

    async def init_api_runtime(self, db_path: str | None = None) -> Any:
        """Initialize a write-capable API runtime for trusted MCP aggregation tools."""
        from app.config import load_config
        from app.di.api import build_api_runtime

        if db_path:
            self.db_path = db_path
        cfg = load_config(allow_stub_telegram=True)
        if cfg.runtime.db_path != self.db_path:
            cfg = replace(
                cfg,
                runtime=cfg.runtime.model_copy(update={"db_path": self.db_path}),
            )
        self._api_runtime = await build_api_runtime(cfg)
        self.logger.info("API runtime connected for MCP aggregation tools: %s", self.db_path)
        return self._api_runtime

    async def ensure_api_runtime(self, db_path: str | None = None) -> Any:
        if self._api_runtime is not None and (db_path is None or db_path == self.db_path):
            return self._api_runtime
        if self._api_runtime_lock is None:
            self._api_runtime_lock = asyncio.Lock()
        async with self._api_runtime_lock:
            if self._api_runtime is not None and (db_path is None or db_path == self.db_path):
                return self._api_runtime
            return await self.init_api_runtime(db_path)

    def request_scope_filters(self, request_model: Any) -> list[Any]:
        filters: list[Any] = [request_model.is_deleted == False]  # noqa: E712
        if self.user_id is not None:
            filters.append(request_model.user_id == self.user_id)
        return filters

    def collection_scope_filters(self, collection_model: Any) -> list[Any]:
        filters: list[Any] = [collection_model.is_deleted == False]  # noqa: E712
        if self.user_id is not None:
            filters.append(collection_model.user == self.user_id)
        return filters

    async def init_chroma_service(self) -> Any:
        """Initialize (or return cached) runtime-owned Chroma search service."""
        service = await mcp_di.ensure_mcp_chroma_service(self.ensure_runtime())
        if service is None:
            self.logger.warning("ChromaDB unavailable — semantic_search tool will be disabled")
        else:
            self.logger.info("ChromaDB search service initialised")
        return service

    async def init_local_vector_service(self) -> Any:
        """Initialize (or return cached) runtime-owned local embedding fallback service."""
        service = await mcp_di.ensure_mcp_local_vector_service(self.ensure_runtime())
        if service is None:
            self.logger.warning("Local vector fallback unavailable")
        else:
            self.logger.info("Local vector fallback service initialised")
        return service

    async def aclose(self) -> None:
        if self._api_runtime is not None:
            from app.di.api import close_api_runtime

            api_runtime = self._api_runtime
            self._api_runtime = None
            await close_api_runtime(api_runtime)
        if self._runtime is None:
            return
        runtime = self._runtime
        self._runtime = None
        await mcp_di.close_mcp_runtime(runtime)
