from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import chromadb
from chromadb.errors import ChromaError

from app.core.logging_utils import get_logger
from app.infrastructure.vector.chroma_schemas import ChromaMetadata, ChromaQueryFilters
from app.infrastructure.vector.result_types import VectorQueryHit, VectorQueryResult

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(__name__)


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
        embedding_space: str | None = None,
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
        self._embedding_space = embedding_space
        self._required = required
        self._connection_timeout = connection_timeout
        self._available = False
        self._client: Any = None
        self._collection: Any = None
        self._collection_name = self._build_collection_name(
            environment, user_scope, collection_version, embedding_space
        )

        # Attempt initial connection with retry for Docker networking race
        self._connect_with_retry()

    def _connect_with_retry(self, max_attempts: int = 3, base_delay: float = 2.0) -> None:
        """Try connecting with brief retries to handle Docker network startup race."""
        for attempt in range(1, max_attempts + 1):
            if self._try_connect():
                return
            if attempt < max_attempts:
                delay = base_delay * attempt
                logger.info(
                    "chroma_connect_retry",
                    extra={"attempt": attempt, "next_delay_sec": delay, "host": self._host},
                )
                asyncio.run(asyncio.sleep(delay))

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
                    chroma_query_request_timeout_seconds=int(self._connection_timeout),
                    anonymized_telemetry=False,
                ),
            )

            # Test connection with heartbeat
            self._client.heartbeat()

            metadata = {
                "hnsw:space": "cosine",
                "environment": self._environment,
                "user_scope": self._user_scope,
                "version": self._collection_version,
            }
            if self._embedding_space is not None:
                metadata["embedding_space"] = self._embedding_space
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata=metadata,
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
    def embedding_space(self) -> str | None:
        return self._embedding_space

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @staticmethod
    def _build_collection_name(
        environment: str,
        user_scope: str,
        version: str,
        embedding_space: str | None = None,
    ) -> str:
        safe_env = environment.replace(" ", "_")
        safe_scope = user_scope.replace(" ", "_")
        safe_version = version.replace(" ", "_")
        base_name = f"notes_{safe_env}_{safe_scope}_{safe_version}"
        if not embedding_space:
            return base_name

        safe_embedding_space = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in str(embedding_space).strip().lower()
        ).strip("_")
        if not safe_embedding_space:
            return base_name
        return f"{base_name}_{safe_embedding_space}"

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

        final_ids, validated_metadata = self._prepare_upsert_payload(metadatas, ids)

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

    def replace_request_notes(
        self,
        request_id: int | str,
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict[str, Any]],
        ids: Sequence[str] | None = None,
    ) -> None:
        """Replace all vectors for a request without dropping data on failed upserts.

        The method upserts the refreshed vectors first, then deletes any stale IDs that
        belonged to the same request but were not part of this write.
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            logger.warning(
                "chroma_replace_skipped",
                extra={"reason": "not_available", "request_id": request_id, "count": len(vectors)},
            )
            return

        if len(vectors) != len(metadatas):
            msg = "Vectors and metadatas must have the same length"
            raise ValueError(msg)

        if ids and len(ids) != len(vectors):
            msg = "IDs must have the same length as vectors"
            raise ValueError(msg)

        final_ids, validated_metadata = self._prepare_upsert_payload(metadatas, ids)
        normalized_request_id = str(request_id)
        metadata_request_ids = {str(metadata["request_id"]) for metadata in validated_metadata}
        if metadata_request_ids != {normalized_request_id}:
            msg = "All metadatas must belong to the same request_id for replacement"
            raise ValueError(msg)

        try:
            collection = cast("Any", self._collection)
            existing_ids = self._fetch_request_ids(collection, request_id)
            collection.upsert(
                embeddings=[list(vector) for vector in vectors],
                metadatas=validated_metadata,
                ids=final_ids,
            )
            stale_ids = sorted(set(existing_ids) - set(final_ids))
            if stale_ids:
                collection.delete(ids=stale_ids)
        except ChromaError as e:
            logger.error(
                "chroma_replace_failed",
                extra={"request_id": request_id, "count": len(vectors), "error": str(e)},
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

    def _prepare_upsert_payload(
        self,
        metadatas: Sequence[dict[str, Any]],
        ids: Sequence[str] | None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        final_ids = list(ids) if ids else [self._extract_id(metadata) for metadata in metadatas]

        validated_metadata = []
        for metadata in metadatas:
            safe_metadata = {
                k: v for k, v in dict(metadata).items() if k not in {"environment", "user_scope"}
            }
            dumped = ChromaMetadata(
                **safe_metadata,
                environment=self._environment,
                user_scope=self._user_scope,
            ).model_dump()
            # Chroma rejects empty list metadata values; drop those keys so the
            # upsert validates. Missing keys are fine; presence with [] is not.
            cleaned = {k: v for k, v in dumped.items() if not (isinstance(v, list) and not v)}
            validated_metadata.append(cleaned)

        return final_ids, validated_metadata

    @staticmethod
    def _normalize_ids(raw_ids: Any) -> list[str]:
        if not raw_ids:
            return []
        if isinstance(raw_ids, list):
            if raw_ids and isinstance(raw_ids[0], list):
                flat: list[str] = []
                for batch in raw_ids:
                    if isinstance(batch, list):
                        flat.extend(str(item) for item in batch if item is not None)
                return flat
            return [str(item) for item in raw_ids if item is not None]
        return [str(raw_ids)]

    def _fetch_request_ids(self, collection: Any, request_id: int | str) -> list[str]:
        payload = collection.get(where={"request_id": request_id})
        if not isinstance(payload, dict):
            return []
        return self._normalize_ids(payload.get("ids"))

    def query(
        self,
        query_vector: Sequence[float],
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> VectorQueryResult:
        """Query for most similar notes.

        When ChromaDB is unavailable and not required, this method returns an
        empty result instead of raising an exception.
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            logger.warning(
                "chroma_query_skipped",
                extra={"reason": "not_available", "top_k": top_k},
            )
            return VectorQueryResult.empty()

        if top_k <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)

        filter_payload = {
            key: value
            for key, value in (filters or {}).items()
            if key not in {"environment", "user_scope"}
        }
        validated_filters = ChromaQueryFilters(
            environment=self._environment,
            user_scope=self._user_scope,
            **filter_payload,
        ).to_where()

        try:
            collection = cast("Any", self._collection)
            raw = cast(
                "dict[str, Any]",
                collection.query(
                    query_embeddings=[list(query_vector)],
                    where=validated_filters,
                    n_results=top_k,
                ),
            )
            return self._raw_to_result(raw)
        except ChromaError as e:
            logger.error(
                "chroma_query_failed",
                extra={"error": str(e)},
            )
            if self._required:
                raise
            self._available = False
            return VectorQueryResult.empty()

    @staticmethod
    def _raw_to_result(raw: dict[str, Any]) -> VectorQueryResult:
        """Convert the Chroma query dict to a VectorQueryResult."""
        ids_batches = raw.get("ids") or [[]]
        dist_batches = raw.get("distances") or [[]]
        meta_batches = raw.get("metadatas") or [[]]

        ids_flat: list[str] = ids_batches[0] if ids_batches else []
        dist_flat: list[float] = dist_batches[0] if dist_batches else []
        meta_flat: list[dict[str, Any]] = meta_batches[0] if meta_batches else []

        hits: list[VectorQueryHit] = []
        for i, point_id in enumerate(ids_flat):
            distance = float(dist_flat[i]) if i < len(dist_flat) else 0.0
            metadata = meta_flat[i] if i < len(meta_flat) else {}
            hits.append(VectorQueryHit(id=str(point_id), distance=distance, metadata=metadata))

        return VectorQueryResult(hits=hits)

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

    def get_indexed_summary_ids(
        self, *, user_id: int | None = None, limit: int | None = 5000
    ) -> set[int]:
        """Return summary IDs currently present in the Chroma collection.

        Args:
            user_id: Optional per-user filter when metadata includes user_id.
            limit: Maximum records to scan (None = backend default/all).
        """
        if not self._available:
            self.ensure_available()
        if not self._available:
            return set()

        where: dict[str, Any] = {
            "environment": self._environment,
            "user_scope": self._user_scope,
        }
        if user_id is not None:
            where["user_id"] = int(user_id)

        try:
            collection = cast("Any", self._collection)
            get_kwargs: dict[str, Any] = {"where": where, "include": ["metadatas"]}
            if limit is not None and limit > 0:
                get_kwargs["limit"] = int(limit)

            payload = cast("dict[str, Any]", collection.get(**get_kwargs))
            metadatas = payload.get("metadatas") or []
            if not isinstance(metadatas, list):
                return set()

            # Chroma can return either flat metadata list or nested list.
            if metadatas and isinstance(metadatas[0], list):
                flat = []
                for batch in metadatas:
                    if isinstance(batch, list):
                        flat.extend(batch)
                metadatas = flat

            summary_ids: set[int] = set()
            for metadata in metadatas:
                if not isinstance(metadata, dict):
                    continue
                raw_summary_id = metadata.get("summary_id")
                try:
                    if raw_summary_id is not None:
                        summary_ids.add(int(raw_summary_id))
                except (TypeError, ValueError):
                    logger.debug(
                        "chroma_summary_id_parse_failed",
                        extra={"raw_summary_id": raw_summary_id},
                    )
                    continue
            return summary_ids
        except ChromaError as e:
            logger.error("chroma_get_indexed_summary_ids_failed", extra={"error": str(e)})
            if self._required:
                raise
            self._available = False
            return set()

    def reset(self) -> None:
        """Reset the collection (for testing purposes)."""
        try:
            self._client.delete_collection(self._collection_name)
            metadata = {
                "hnsw:space": "cosine",
                "environment": self._environment,
                "user_scope": self._user_scope,
                "version": self._collection_version,
            }
            if self._embedding_space is not None:
                metadata["embedding_space"] = self._embedding_space
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata=metadata,
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
