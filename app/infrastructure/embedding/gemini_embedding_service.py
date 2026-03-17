"""Embedding service backed by Google Gemini Embedding 2 API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.infrastructure.embedding.embedding_protocol import EmbeddingSerializationMixin

logger = logging.getLogger(__name__)

# Task type mapping: caller-friendly names -> Gemini API enum values
_TASK_TYPE_MAP: dict[str | None, str] = {
    "document": "RETRIEVAL_DOCUMENT",
    "query": "RETRIEVAL_QUERY",
    None: "SEMANTIC_SIMILARITY",
}


class GeminiEmbeddingService(EmbeddingSerializationMixin):
    """Generate embeddings via Google Gemini Embedding API.

    Uses lazy import of ``google.genai`` so the app works without the
    dependency when ``EMBEDDING_PROVIDER=local``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-2-preview",
        dimensions: int = 768,
    ) -> None:
        if not api_key:
            msg = "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini"
            raise ValueError(msg)
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        """Lazily initialise the google-genai client."""
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
            logger.info(
                "gemini_embedding_client_initialized",
                extra={"model": self._model, "dimensions": self._dimensions},
            )
        return self._client

    async def generate_embedding(
        self,
        text: str,
        *,
        language: str | None = None,
        task_type: str | None = None,
    ) -> list[float]:
        """Generate embedding via Gemini API.

        Args:
            text: Text to embed.
            language: Ignored (Gemini is natively multilingual).
            task_type: One of ``"document"``, ``"query"``, or ``None``.
        """
        client = self._ensure_client()
        gemini_task = _TASK_TYPE_MAP.get(task_type, "SEMANTIC_SIMILARITY")

        result = await asyncio.to_thread(
            client.models.embed_content,
            model=self._model,
            contents=text,
            config={
                "task_type": gemini_task,
                "output_dimensionality": self._dimensions,
            },
        )

        values: list[float] = result.embeddings[0].values
        return values

    # -- Metadata --------------------------------------------------------------

    def get_model_name(self, language: str | None = None) -> str:
        return self._model

    def get_dimensions(self, language: str | None = None) -> int:
        return self._dimensions

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        self._client = None

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)
