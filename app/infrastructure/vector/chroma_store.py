from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import chromadb
from chromadb.errors import ChromaError

from app.infrastructure.vector.chroma_schemas import ChromaMetadata, ChromaQueryFilters

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Wrapper around Chroma client for note embeddings.

    Supports graceful degradation when ChromaDB is unavailable. When `required=False`
    (default), the store will log warnings but not raise exceptions on connection
    failures, allowing the application to continue without vector search functionality.
    """

    def __init__(
        self,
        *,
        host: str,
        auth_token: str | None,
        environment: str,
        user_scope: str,
        collection_version: str = "v1",
        required: bool = False,
        connection_timeout: float = 10.0,
    ) -> None:
        if not host:
            msg = "Chroma host must be provided"
            raise ValueError(msg)

        self._host = host
        self._auth_token = auth_token
        self._environment = environment
        self._user_scope = user_scope
        self._collection_version = collection_version
        self._required = required
        self._connection_timeout = connection_timeout
        self._available = False
        self._client: Any = None
        self._collection: Any = None
        self._collection_name = self._build_collection_name(
            environment, user_scope, collection_version
        )

        # Attempt initial connection
        self._try_connect()

    def _try_connect(self) -> bool:
        """Attempt to connect to ChromaDB.

        Returns:
            True if connection successful, False otherwise.
        """
        headers = {"Authorization": f"Bearer {self._auth_token}"} if self._auth_token else None
        try:
            self._client = chromadb.HttpClient(
                host=self._host,
                headers=headers,
                settings=chromadb.Settings(
                    chroma_query_request_timeout_seconds=self._connection_timeout,
                    anonymized_telemetry=False,
                ),
            )

            # Test connection with heartbeat
            self._client.heartbeat()

            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "environment": self._environment,
                    "user_scope": self._user_scope,
                    "version": self._collection_version,
                },
            )
            self._available = True
            logger.info(
                "chroma_collection_initialized",
                extra={
                    "collection": self._collection_name,
                    "host": self._host,
                    "environment": self._environment,
                    "version": self._collection_version,
                },
            )
            return True
        except Exception as e:
            logger.error(
                "chroma_initialization_failed",
                extra={
                    "host": self._host,
                    "error": str(e),
                    "required": self._required,
                },
            )
            self._available = False
            if self._required:
                raise
            return False

    @property
    def available(self) -> bool:
        """Check if ChromaDB is available and connected."""
        return self._available

    def ensure_available(self) -> bool:
        """Ensure ChromaDB is available, attempting reconnect if needed.

        Returns:
            True if ChromaDB is available after this call.
        """
        if self._available:
            return True
        logger.info("chroma_reconnect_attempt", extra={"host": self._host})
        return self._try_connect()

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def user_scope(self) -> str:
        return self._user_scope

    @property
    def collection_version(self) -> str:
        return self._collection_version

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @staticmethod
    def _build_collection_name(environment: str, user_scope: str, version: str) -> str:
        safe_env = environment.replace(" ", "_")
        safe_scope = user_scope.replace(" ", "_")
        safe_version = version.replace(" ", "_")
        return f"notes_{safe_env}_{safe_scope}_{safe_version}"

    def upsert_notes(
        self,
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, Any]],
        ids: Sequence[str] | None = None,
    ) -> None:
        """Upsert note embeddings with associated metadata.

        When ChromaDB is unavailable and not required, this method logs a warning
        and returns without raising an exception.
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            logger.warning(
                "chroma_upsert_skipped",
                extra={"reason": "not_available", "count": len(vectors)},
            )
            return

        if len(vectors) != len(metadatas):
            msg = "Vectors and metadatas must have the same length"
            raise ValueError(msg)

        if ids and len(ids) != len(vectors):
            msg = "IDs must have the same length as vectors"
            raise ValueError(msg)

        final_ids = list(ids) if ids else [self._extract_id(metadata) for metadata in metadatas]

        validated_metadata = []
        for metadata in metadatas:
            safe_metadata = {
                k: v for k, v in dict(metadata).items() if k not in {"environment", "user_scope"}
            }
            validated_metadata.append(
                ChromaMetadata(
                    **safe_metadata,
                    environment=self._environment,
                    user_scope=self._user_scope,
                ).model_dump()
            )

        try:
            collection = cast("Any", self._collection)
            collection.upsert(
                embeddings=[list(vector) for vector in vectors],
                metadatas=validated_metadata,
                ids=final_ids,
            )
        except ChromaError as e:
            logger.error(
                "chroma_upsert_failed",
                extra={"count": len(vectors), "error": str(e)},
            )
            if self._required:
                raise
            self._available = False

    @staticmethod
    def _extract_id(metadata: dict[str, Any]) -> str:
        request_id = metadata.get("request_id")
        summary_id = metadata.get("summary_id")
        chunk_id = metadata.get("chunk_id")
        window_id = metadata.get("window_id")

        if request_id is not None:
            base = str(request_id)
            if chunk_id:
                return f"{base}:{chunk_id}"
            if window_id:
                return f"{base}:{window_id}"
            if summary_id is not None:
                return f"{base}:{summary_id}"
            return base

        return uuid4().hex

    def query(
        self,
        query_vector: Sequence[float],
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> dict[str, Any]:
        """Query for most similar notes.

        When ChromaDB is unavailable and not required, this method returns empty
        results instead of raising an exception.
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            logger.warning(
                "chroma_query_skipped",
                extra={"reason": "not_available", "top_k": top_k},
            )
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}

        if top_k <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)

        filter_payload = dict(filters or {})
        filter_payload.pop("environment", None)
        filter_payload.pop("user_scope", None)
        validated_filters = ChromaQueryFilters(
            environment=self._environment,
            user_scope=self._user_scope,
            **filter_payload,
        ).to_where()

        try:
            collection = cast("Any", self._collection)
            result = collection.query(
                query_embeddings=[list(query_vector)],
                where=validated_filters,
                n_results=top_k,
            )
            return cast("dict[str, Any]", result)
        except ChromaError as e:
            logger.error(
                "chroma_query_failed",
                extra={"error": str(e)},
            )
            if self._required:
                raise
            self._available = False
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    def delete_by_request_id(self, request_id: int | str) -> None:
        """Delete embeddings associated with a specific request ID.

        When ChromaDB is unavailable, logs a warning and returns.
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            logger.warning(
                "chroma_delete_skipped",
                extra={"reason": "not_available", "request_id": request_id},
            )
            return

        try:
            self._collection.delete(where={"request_id": request_id})
        except ChromaError as e:
            logger.error(
                "chroma_delete_failed",
                extra={"request_id": request_id, "error": str(e)},
            )
            if self._required:
                raise
            self._available = False

    def health_check(self) -> bool:
        """Check if ChromaDB is reachable and functioning."""
        if not self._available:
            self.ensure_available()
        if not self._available or not self._client:
            return False
        try:
            self._client.heartbeat()
            return True
        except Exception:
            self._available = False
            return False

    def reset(self) -> None:
        """Reset the collection (for testing purposes)."""
        try:
            self._client.delete_collection(self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "environment": self._environment,
                    "user_scope": self._user_scope,
                    "version": self._collection_version,
                },
            )
        except Exception as e:
            logger.error("chroma_reset_failed", extra={"error": str(e)})
            raise

    def count(self) -> int:
        """Count the number of items in the collection."""
        if not self._available:
            self.ensure_available()
        if not self._available:
            return 0
        return self._collection.count()

    def close(self) -> None:
        """Close underlying Chroma client connections."""
        client = getattr(self, "_client", None)
        if client is None:
            return

        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
                return
            except Exception as e:  # pragma: no cover - defensive close
                logger.warning("chroma_client_close_failed", extra={"error": str(e)})

        session = getattr(client, "_session", None)
        if session:
            close_session = getattr(session, "close", None)
            if callable(close_session):
                try:
                    close_session()
                except Exception as e:  # pragma: no cover - defensive close
                    logger.warning("chroma_session_close_failed", extra={"error": str(e)})

    async def aclose(self) -> None:
        """Async wrapper for close()."""
        try:
            await asyncio.to_thread(self.close)
        except Exception:  # pragma: no cover - defensive close
            logger.exception("chroma_client_async_close_failed")
