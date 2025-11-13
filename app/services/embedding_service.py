"""Service for generating and managing semantic embeddings for articles."""

from __future__ import annotations

import asyncio
import logging
import pickle
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate and manage semantic embeddings for articles."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None

    def _ensure_model(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            # Get embedding dimensions
            sample = self._model.encode("test")
            self._dimensions = len(sample)
            logger.info(
                "embedding_model_loaded",
                extra={"model": self._model_name, "dims": self._dimensions},
            )
        return self._model

    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding vector for text."""
        model = self._ensure_model()

        # Run in thread pool to avoid blocking
        embedding = await asyncio.to_thread(
            model.encode, text, convert_to_numpy=True, show_progress_bar=False
        )
        return embedding

    def serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize numpy array to bytes for database storage."""
        return pickle.dumps(embedding, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize_embedding(self, blob: bytes) -> np.ndarray:
        """Deserialize embedding from database."""
        return pickle.loads(blob)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int | None:
        """Get embedding dimensions (None if model not loaded)."""
        if self._dimensions is None and self._model is not None:
            self._ensure_model()
        return self._dimensions


def prepare_text_for_embedding(
    *,
    title: str | None,
    summary_1000: str | None,
    summary_250: str | None,
    tldr: str | None,
    key_ideas: list[str] | None = None,
    topic_tags: list[str] | None = None,
    max_length: int = 512,
) -> str:
    """Compose optimized text for embedding generation.

    Combines multiple fields into a single text that captures the
    article's semantic meaning.
    """
    parts = []

    # Title gets extra weight by including twice
    if title:
        parts.append(title)
        parts.append(title)

    # Primary content
    if summary_1000:
        parts.append(summary_1000)
    elif summary_250:
        parts.append(summary_250)
    elif tldr:
        parts.append(tldr)

    # Key ideas for semantic context
    if key_ideas:
        parts.extend(key_ideas[:5])  # Top 5 ideas

    # Tags for topic context
    if topic_tags:
        # Remove hashtags for cleaner embedding
        clean_tags = [tag.lstrip("#") for tag in topic_tags[:5]]
        parts.extend(clean_tags)

    # Combine and truncate
    text = " ".join(parts)

    # Rough token estimation (4 chars ≈ 1 token)
    if len(text) > max_length * 4:
        text = text[: max_length * 4]

    return text.strip()
