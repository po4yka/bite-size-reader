from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import chromadb
from chromadb.errors import ChromaError

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Wrapper around Chroma client for note embeddings."""

    def __init__(
        self,
        *,
        host: str,
        auth_token: str | None,
        environment: str,
        user_scope: str,
    ) -> None:
        if not host:
            msg = "Chroma host must be provided"
            raise ValueError(msg)

        self._host = host
        self._environment = environment
        self._user_scope = user_scope

        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        try:
            self._client = chromadb.HttpClient(host=host, headers=headers)
            self._collection_name = self._build_collection_name(environment, user_scope)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"environment": environment, "user_scope": user_scope},
            )
            logger.info(
                "chroma_collection_initialized",
                extra={
                    "collection": self._collection_name,
                    "host": host,
                    "environment": environment,
                },
            )
        except Exception as e:
            logger.error(
                "chroma_initialization_failed",
                extra={"host": host, "error": str(e)},
            )
            raise

    @staticmethod
    def _build_collection_name(environment: str, user_scope: str) -> str:
        safe_env = environment.replace(" ", "_")
        safe_scope = user_scope.replace(" ", "_")
        return f"notes_{safe_env}_{safe_scope}"

    def upsert_notes(
        self,
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, Any]],
        ids: Sequence[str] | None = None,
    ) -> None:
        """Upsert note embeddings with associated metadata."""
        if len(vectors) != len(metadatas):
            msg = "Vectors and metadatas must have the same length"
            raise ValueError(msg)

        if ids and len(ids) != len(vectors):
            msg = "IDs must have the same length as vectors"
            raise ValueError(msg)

        final_ids = list(ids) if ids else [self._extract_id(metadata) for metadata in metadatas]

        try:
            self._collection.upsert(
                embeddings=[list(vector) for vector in vectors],
                metadatas=[dict(metadata) for metadata in metadatas],
                ids=final_ids,
            )
        except ChromaError as e:
            logger.error(
                "chroma_upsert_failed",
                extra={"count": len(vectors), "error": str(e)},
            )
            raise

    @staticmethod
    def _extract_id(metadata: dict[str, Any]) -> str:
        request_id = metadata.get("request_id")
        if request_id is None:
            return uuid4().hex
        return str(request_id)

    def query(
        self,
        query_vector: Sequence[float],
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> dict[str, Any]:
        """Query for most similar notes."""
        if top_k <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)

        try:
            return self._collection.query(
                query_embeddings=[list(query_vector)],
                where=filters or {},
                n_results=top_k,
            )
        except ChromaError as e:
            logger.error(
                "chroma_query_failed",
                extra={"error": str(e)},
            )
            raise

    def delete_by_request_id(self, request_id: int | str) -> None:
        """Delete embeddings associated with a specific request ID."""
        try:
            self._collection.delete(where={"request_id": request_id})
        except ChromaError as e:
            logger.error(
                "chroma_delete_failed",
                extra={"request_id": request_id, "error": str(e)},
            )
            raise

    def health_check(self) -> bool:
        """Check if ChromaDB is reachable and functioning."""
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False

    def reset(self) -> None:
        """Reset the collection (for testing purposes)."""
        try:
            self._client.delete_collection(self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"environment": self._environment, "user_scope": self._user_scope},
            )
        except Exception as e:
            logger.error("chroma_reset_failed", extra={"error": str(e)})
            raise

    def count(self) -> int:
        """Count the number of items in the collection."""
        return self._collection.count()
