from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import chromadb

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

        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        self._client = chromadb.HttpClient(host=host, headers=headers)
        self._collection_name = self._build_collection_name(environment, user_scope)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"environment": environment, "user_scope": user_scope},
        )

        logger.info(
            "chroma_collection_initialized",
            extra={"collection": self._collection_name, "host": host, "environment": environment},
        )

    @staticmethod
    def _build_collection_name(environment: str, user_scope: str) -> str:
        safe_env = environment.replace(" ", "_")
        safe_scope = user_scope.replace(" ", "_")
        return f"notes_{safe_env}_{safe_scope}"

    def upsert_notes(
        self,
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        """Upsert note embeddings with associated metadata."""
        if len(vectors) != len(metadatas):
            msg = "Vectors and metadatas must have the same length"
            raise ValueError(msg)

        ids = [self._extract_id(metadata) for metadata in metadatas]
        self._collection.upsert(
            embeddings=[list(vector) for vector in vectors],
            metadatas=[dict(metadata) for metadata in metadatas],
            ids=ids,
        )

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

        return self._collection.query(
            query_embeddings=[list(query_vector)],
            where=filters or {},
            n_results=top_k,
        )

    def delete_by_request_id(self, request_id: int | str) -> None:
        """Delete embeddings associated with a specific request ID."""
        self._collection.delete(where={"request_id": request_id})
