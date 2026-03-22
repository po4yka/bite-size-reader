"""Application service for generating embeddings for summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.embedding_text import prepare_text_for_embedding
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.application.ports.requests import RequestRepositoryPort
    from app.application.ports.search import EmbeddingProviderPort, EmbeddingRepositoryPort
    from app.application.ports.summaries import SummaryRepositoryPort

logger = get_logger(__name__)


class SummaryEmbeddingGenerator:
    """Generates and stores embeddings for article summaries."""

    def __init__(
        self,
        *,
        embedding_repository: EmbeddingRepositoryPort,
        request_repository: RequestRepositoryPort,
        summary_repository: SummaryRepositoryPort,
        embedding_service: EmbeddingProviderPort,
        model_version: str = "1.0",
        max_token_length: int = 512,
    ) -> None:
        self.embedding_repo = embedding_repository
        self.request_repo = request_repository
        self.summary_repo = summary_repository
        self._embedding_service = embedding_service
        self._model_version = model_version
        self._max_token_length = max_token_length

    @property
    def embedding_service(self) -> EmbeddingProviderPort:
        """Expose the embedding provider in use."""
        return self._embedding_service

    async def generate_embedding_for_summary(
        self,
        summary_id: int,
        payload: dict[str, Any],
        *,
        language: str | None = None,
        force: bool = False,
    ) -> bool:
        """Generate and store an embedding for a specific summary."""
        model_name = self._embedding_service.get_model_name(language)
        if not force:
            existing = await self.embedding_repo.async_get_summary_embedding(summary_id)
            if existing and existing.get("model_name") == model_name:
                logger.debug(
                    "embedding_already_exists",
                    extra={"summary_id": summary_id, "model": model_name, "language": language},
                )
                return False

        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        try:
            text = prepare_text_for_embedding(
                title=metadata.get("title") or payload.get("title"),
                summary_1000=payload.get("summary_1000"),
                summary_250=payload.get("summary_250"),
                tldr=payload.get("tldr"),
                key_ideas=payload.get("key_ideas"),
                topic_tags=payload.get("topic_tags"),
                semantic_boosters=payload.get("semantic_boosters"),
                query_expansion_keywords=payload.get("query_expansion_keywords"),
                semantic_chunks=payload.get("semantic_chunks"),
                max_length=self._max_token_length,
            )
            if not text.strip():
                logger.warning("empty_text_for_embedding", extra={"summary_id": summary_id})
                return False

            embedding = await self._embedding_service.generate_embedding(
                text,
                language=language,
                task_type="document",
            )
            await self.embedding_repo.async_create_or_update_summary_embedding(
                summary_id=summary_id,
                embedding_blob=self._embedding_service.serialize_embedding(embedding),
                model_name=model_name,
                model_version=self._model_version,
                dimensions=len(embedding),
                language=language,
            )
            logger.info(
                "embedding_generated",
                extra={
                    "summary_id": summary_id,
                    "model": model_name,
                    "language": language,
                    "dimensions": len(embedding),
                    "text_length": len(text),
                },
            )
            return True
        except (RuntimeError, ValueError, OSError, TypeError):
            logger.exception(
                "embedding_generation_failed",
                extra={"summary_id": summary_id, "language": language},
            )
            return False

    async def generate_embedding_for_request(self, request_id: int, *, force: bool = False) -> bool:
        """Generate an embedding for the summary produced by a request."""
        request = await self.request_repo.async_get_request_by_id(request_id)
        if not request:
            logger.warning("no_request_found", extra={"request_id": request_id})
            return False

        summary = await self.summary_repo.async_get_summary_by_request(request_id)
        if not summary:
            logger.warning("no_summary_for_request", extra={"request_id": request_id})
            return False

        summary_id = summary.get("id")
        payload = summary.get("json_payload")
        if not summary_id or not isinstance(payload, dict):
            logger.warning(
                "invalid_summary_data",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            return False

        return await self.generate_embedding_for_summary(
            summary_id=summary_id,
            payload=payload,
            language=request.get("lang_detected"),
            force=force,
        )
