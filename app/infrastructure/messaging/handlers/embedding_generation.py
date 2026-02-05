"""Embedding generation event handler."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.events.summary_events import SummaryCreated
    from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
        SqliteSummaryRepositoryAdapter,
    )

logger = logging.getLogger(__name__)


class EmbeddingGenerationEventHandler:
    """Generate vector embeddings for new summaries."""

    def __init__(
        self,
        embedding_generator: Any,
        summary_repository: SqliteSummaryRepositoryAdapter,
        vector_store: Any | None = None,
    ) -> None:
        self._generator = embedding_generator
        self._summary_repo = summary_repository
        self._vector_store = vector_store

    async def on_summary_created(self, event: SummaryCreated) -> None:
        logger.info(
            "generating_embedding_for_new_summary",
            extra={"summary_id": event.summary_id, "request_id": event.request_id},
        )

        try:
            success = await self._generator.generate_embedding_for_request(
                request_id=event.request_id,
                force=False,
            )

            if success:
                logger.info(
                    "embedding_generated_successfully",
                    extra={"summary_id": event.summary_id, "request_id": event.request_id},
                )
            else:
                logger.debug(
                    "embedding_generation_skipped",
                    extra={
                        "summary_id": event.summary_id,
                        "request_id": event.request_id,
                        "reason": "already_exists_or_empty",
                    },
                )

            await self._sync_vector_store(event.request_id)

        except Exception as exc:
            logger.exception(
                "embedding_generation_failed",
                extra={
                    "summary_id": event.summary_id,
                    "request_id": event.request_id,
                    "error": str(exc),
                },
            )

    async def _sync_vector_store(self, request_id: int) -> None:
        if not self._vector_store:
            return

        embedding_service = getattr(self._generator, "embedding_service", None)
        if embedding_service is None:
            logger.warning(
                "vector_store_sync_unavailable",
                extra={"request_id": request_id, "reason": "missing_dependencies"},
            )
            return

        summary = await self._summary_repo.async_get_summary_by_request(request_id)
        if not summary:
            logger.info("vector_store_delete_missing_summary", extra={"request_id": request_id})
            await asyncio.to_thread(self._vector_store.delete_by_request_id, request_id)
            return

        payload = summary.get("json_payload")
        summary_id = summary.get("id")
        if not payload or not summary_id:
            logger.info(
                "vector_store_delete_empty_payload",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            await asyncio.to_thread(self._vector_store.delete_by_request_id, request_id)
            return

        from app.services.metadata_builder import MetadataBuilder

        user_scope = getattr(self._vector_store, "user_scope", None) or "public"
        environment = getattr(self._vector_store, "environment", None) or "dev"

        chunk_windows = MetadataBuilder.prepare_chunk_windows_for_upsert(
            request_id=request_id,
            summary_id=summary_id,
            payload=payload,
            language=self._determine_language(summary),
            user_scope=user_scope,
            environment=environment,
        )

        vectors: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        if chunk_windows:
            for text, metadata in chunk_windows:
                embedding = await embedding_service.generate_embedding(
                    text, language=metadata.get("language")
                )
                vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                vectors.append(vector)
                metadatas.append(metadata)
        else:
            text, metadata = MetadataBuilder.prepare_for_upsert(
                request_id=request_id,
                summary_id=summary_id,
                payload=payload,
                language=self._determine_language(summary),
                user_scope=user_scope,
                environment=environment,
                summary_row=summary,
            )

            if not text:
                logger.info(
                    "vector_store_delete_empty_note",
                    extra={"request_id": request_id, "summary_id": summary_id},
                )
                await asyncio.to_thread(self._vector_store.delete_by_request_id, request_id)
                return

            embedding = await embedding_service.generate_embedding(
                text, language=metadata.get("language")
            )
            vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            vectors.append(vector)
            metadatas.append(metadata)

        if not vectors:
            logger.info(
                "vector_store_delete_empty_note",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            await asyncio.to_thread(self._vector_store.delete_by_request_id, request_id)
            return

        await asyncio.to_thread(self._vector_store.upsert_notes, vectors, metadatas)

        logger.info(
            "vector_store_synced",
            extra={
                "request_id": request_id,
                "summary_id": summary_id,
                "metadata_keys": sorted(metadatas[0].keys()) if metadatas else [],
                "vector_count": len(vectors),
            },
        )

    @staticmethod
    def _determine_language(summary: dict[str, Any]) -> str | None:
        if not summary:
            return None

        language = summary.get("lang") or summary.get("language")
        if language:
            return language

        request_data = summary.get("request") or {}
        if isinstance(request_data, dict):
            return request_data.get("lang_detected")
        return None
