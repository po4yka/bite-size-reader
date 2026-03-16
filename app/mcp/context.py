from __future__ import annotations

import logging
import os
from typing import Any

import app.di.mcp as mcp_di


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
        self._user_id = user_id
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
        return self._runtime.scope.user_id if self._runtime is not None else self._user_id

    @property
    def runtime(self) -> Any | None:
        return self._runtime

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
        self._runtime = mcp_di.build_mcp_runtime(db_path=self.db_path, user_id=self.user_id)
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

    async def get_chroma_service(self) -> Any:
        """Return the runtime-owned Chroma search service."""
        mcp_di.CHROMA_RETRY_INTERVAL_SEC = self._chroma_retry_interval_sec
        service = await mcp_di.get_mcp_chroma_service(self.ensure_runtime())
        if service is None:
            self.logger.warning("ChromaDB unavailable — semantic_search tool will be disabled")
        else:
            self.logger.info("ChromaDB search service initialised")
        return service

    async def get_local_vector_service(self) -> Any:
        """Return the runtime-owned local embedding fallback service."""
        mcp_di.LOCAL_VECTOR_RETRY_INTERVAL_SEC = self._local_vector_retry_interval_sec
        service = await mcp_di.get_mcp_local_vector_service(self.ensure_runtime())
        if service is None:
            self.logger.warning("Local vector fallback unavailable")
        else:
            self.logger.info("Local vector fallback service initialised")
        return service

    async def aclose(self) -> None:
        if self._runtime is None:
            return
        runtime = self._runtime
        self._runtime = None
        await mcp_di.close_mcp_runtime(runtime)
