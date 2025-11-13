"""Service for generating and managing semantic embeddings for articles."""

from __future__ import annotations

import asyncio
import logging
import pickle
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


# Language-specific model configuration
# Maps language codes to optimal embedding models
DEFAULT_MODELS = {
    "en": "all-MiniLM-L6-v2",  # English-optimized, 384 dims
    "ru": "paraphrase-multilingual-MiniLM-L12-v2",  # Multilingual, good for Russian, 384 dims
    "auto": "paraphrase-multilingual-MiniLM-L12-v2",  # Default multilingual model, 384 dims
}


class EmbeddingService:
    """Generate and manage semantic embeddings for articles with multi-language support."""

    def __init__(
        self,
        default_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
        model_registry: dict[str, str] | None = None,
    ) -> None:
        """Initialize embedding service with multi-language support.

        Args:
            default_model: Default model to use when language is not specified
            model_registry: Custom mapping of language codes to model names
                           If None, uses DEFAULT_MODELS
        """
        self._default_model = default_model
        self._model_registry = model_registry or DEFAULT_MODELS.copy()
        self._models: dict[str, SentenceTransformer] = {}  # Model cache per language
        self._dimensions: dict[str, int] = {}  # Dimensions per model

    def _get_model_name_for_language(self, language: str | None) -> str:
        """Get the appropriate model name for a language."""
        if not language:
            return self._default_model

        # Check registry
        return self._model_registry.get(language, self._default_model)

    def _ensure_model(self, model_name: str) -> SentenceTransformer:
        """Lazy load the embedding model (cached per model name)."""
        if model_name not in self._models:
            from sentence_transformers import SentenceTransformer

            self._models[model_name] = SentenceTransformer(model_name)
            # Get embedding dimensions
            sample = self._models[model_name].encode("test")
            self._dimensions[model_name] = len(sample)
            logger.info(
                "embedding_model_loaded",
                extra={"model": model_name, "dims": self._dimensions[model_name]},
            )
        return self._models[model_name]

    async def generate_embedding(self, text: str, language: str | None = None) -> Any:
        """Generate embedding vector for text.

        Args:
            text: Text to embed
            language: Language code (en, ru, auto) to select optimal model

        Returns:
            Numpy array embedding vector
        """
        model_name = self._get_model_name_for_language(language)
        model = self._ensure_model(model_name)

        # Run in thread pool to avoid blocking
        return await asyncio.to_thread(
            model.encode, text, convert_to_numpy=True, show_progress_bar=False
        )

    def serialize_embedding(self, embedding: Any) -> bytes:
        """Serialize numpy array to bytes for database storage."""
        return pickle.dumps(embedding, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize_embedding(self, blob: bytes) -> Any:
        """Deserialize embedding from database."""
        return pickle.loads(blob)

    def get_model_name(self, language: str | None = None) -> str:
        """Get model name for a specific language."""
        return self._get_model_name_for_language(language)

    def get_dimensions(self, language: str | None = None) -> int:
        """Get embedding dimensions for a specific language.

        Loads the model if not already loaded.
        """
        model_name = self._get_model_name_for_language(language)
        if model_name not in self._dimensions:
            self._ensure_model(model_name)
        return self._dimensions[model_name]

    @property
    def model_name(self) -> str:
        """Get default model name (for backward compatibility)."""
        return self._default_model

    @property
    def dimensions(self) -> int:
        """Get default model dimensions (for backward compatibility)."""
        return self.get_dimensions(None)


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
