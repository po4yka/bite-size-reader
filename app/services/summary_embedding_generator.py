"""Service for generating embeddings for summaries automatically."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.embedding_service import EmbeddingService, prepare_text_for_embedding

if TYPE_CHECKING:
    from app.db.database import Database

logger = logging.getLogger(__name__)


class SummaryEmbeddingGenerator:
    """Generates and stores embeddings for article summaries."""

    def __init__(
        self,
        db: Database,
        embedding_service: EmbeddingService | None = None,
        model_version: str = "1.0",
    ) -> None:
        self._db = db
        self._embedding_service = embedding_service or EmbeddingService()
        self._model_version = model_version

    @property
    def db(self) -> Database:
        """Expose the underlying database instance."""

        return self._db

    @property
    def embedding_service(self) -> EmbeddingService:
        """Expose the embedding service in use."""

        return self._embedding_service

    async def generate_embedding_for_summary(
        self,
        summary_id: int,
        payload: dict[str, Any],
        *,
        language: str | None = None,
        force: bool = False,
    ) -> bool:
        """Generate and store embedding for a summary.

        Args:
            summary_id: ID of the summary
            payload: Summary JSON payload containing title, summaries, etc.
            language: Language code (en, ru, auto) - if None, uses default model
            force: If True, regenerate embedding even if one exists

        Returns:
            True if embedding was generated, False if skipped or failed
        """
        # Determine model based on language
        model_name = self._embedding_service.get_model_name(language)

        # Check if embedding already exists
        if not force:
            existing = await self._db.async_get_summary_embedding(summary_id)
            if existing and existing.get("model_name") == model_name:
                logger.debug(
                    "embedding_already_exists",
                    extra={
                        "summary_id": summary_id,
                        "model": existing.get("model_name"),
                        "language": language,
                    },
                )
                return False

        # Extract fields from payload
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

        try:
            # Prepare text for embedding
            text = prepare_text_for_embedding(
                title=metadata.get("title") or payload.get("title"),
                summary_1000=payload.get("summary_1000"),
                summary_250=payload.get("summary_250"),
                tldr=payload.get("tldr"),
                key_ideas=payload.get("key_ideas"),
                topic_tags=payload.get("topic_tags"),
            )

            if not text or not text.strip():
                logger.warning(
                    "empty_text_for_embedding",
                    extra={"summary_id": summary_id},
                )
                return False

            # Generate embedding with language-specific model
            embedding = await self._embedding_service.generate_embedding(text, language=language)

            # Serialize and store
            embedding_blob = self._embedding_service.serialize_embedding(embedding)
            dimensions = len(embedding)

            await self._db.async_create_or_update_summary_embedding(
                summary_id=summary_id,
                embedding_blob=embedding_blob,
                model_name=model_name,
                model_version=self._model_version,
                dimensions=dimensions,
                language=language,
            )

            logger.info(
                "embedding_generated",
                extra={
                    "summary_id": summary_id,
                    "model": model_name,
                    "language": language,
                    "dimensions": dimensions,
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

    async def generate_embedding_for_request(
        self,
        request_id: int,
        *,
        force: bool = False,
    ) -> bool:
        """Generate embedding for a summary by request ID.

        Args:
            request_id: ID of the request
            force: If True, regenerate embedding even if one exists

        Returns:
            True if embedding was generated, False if skipped or failed
        """
        # Fetch request to get language
        request = await self._db.async_get_request_by_id(request_id)
        if not request:
            logger.warning(
                "no_request_found",
                extra={"request_id": request_id},
            )
            return False

        # Extract detected language
        language = request.get("lang_detected")

        # Fetch summary
        summary = await self._db.async_get_summary_by_request(request_id)
        if not summary:
            logger.warning(
                "no_summary_for_request",
                extra={"request_id": request_id},
            )
            return False

        summary_id = summary.get("id")
        payload = summary.get("json_payload")

        if not summary_id or not payload:
            logger.warning(
                "invalid_summary_data",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            return False

        return await self.generate_embedding_for_summary(
            summary_id=summary_id,
            payload=payload,
            language=language,
            force=force,
        )
