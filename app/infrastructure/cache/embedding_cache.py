"""Redis cache for embedding vectors.

Caches computed embeddings by content hash to avoid recomputation.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import struct
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.infrastructure.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Cache computed embedding vectors in Redis.

    Key pattern: bsr:embed:v1:{model_name}:{content_hash}
    Value: {"embedding": base64_encoded_float32_array, "dimensions": int}
    TTL: 24 hours (configurable via REDIS_EMBEDDING_CACHE_TTL_SECONDS)

    Why cache embeddings?
    - Embedding generation is CPU-intensive (especially on ARM/Pi)
    - Same content produces identical embeddings
    - Many articles get re-processed (edits, re-summarization)

    Fallback: On cache miss, compute embedding (existing behavior).
    """

    def __init__(self, cache: RedisCache, cfg: AppConfig) -> None:
        self._cache = cache
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    @staticmethod
    def hash_content(text: str) -> str:
        """Create a deterministic hash for content.

        Uses SHA256 truncated to 32 chars for reasonable key length.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def serialize_embedding(embedding: Any) -> str:
        """Serialize embedding vector to base64 string.

        Args:
            embedding: Numpy array or list of floats.

        Returns:
            Base64-encoded string of packed float32 values.
        """
        values: list[float] = (
            embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        )
        packed = struct.pack(f"<{len(values)}f", *values)
        return base64.b64encode(packed).decode("ascii")

    @staticmethod
    def deserialize_embedding(encoded: str) -> list[float]:
        """Deserialize embedding from base64 string.

        Args:
            encoded: Base64-encoded string.

        Returns:
            List of float values.
        """
        packed = base64.b64decode(encoded)
        count = len(packed) // 4  # 4 bytes per float32
        return list(struct.unpack(f"<{count}f", packed))

    async def get(
        self,
        content_hash: str,
        model_name: str,
    ) -> list[float] | None:
        """Get cached embedding by content hash.

        Args:
            content_hash: SHA256 hash of the content.
            model_name: Embedding model name (for cache partitioning).

        Returns:
            List of float values or None if not cached.
        """
        if not self._cache.enabled:
            return None

        cached = await self._cache.get_json("embed", "v1", model_name, content_hash)
        if not isinstance(cached, dict):
            return None

        embedding_b64 = cached.get("embedding")
        if not isinstance(embedding_b64, str):
            return None

        try:
            embedding = self.deserialize_embedding(embedding_b64)
            logger.debug(
                "embedding_cache_hit",
                extra={
                    "model": model_name,
                    "hash": content_hash[:8],
                    "dimensions": len(embedding),
                },
            )
            return embedding
        except Exception as exc:
            logger.warning(
                "embedding_cache_deserialize_failed",
                extra={"hash": content_hash[:8], "error": str(exc)},
            )
            return None

    async def set(
        self,
        content_hash: str,
        model_name: str,
        embedding: Any,
    ) -> bool:
        """Cache an embedding vector.

        Args:
            content_hash: SHA256 hash of the content.
            model_name: Embedding model name.
            embedding: Numpy array or list of floats.

        Returns:
            True if cached successfully, False otherwise.
        """
        if not self._cache.enabled:
            return False

        try:
            embedding_b64 = self.serialize_embedding(embedding)
        except Exception as exc:
            logger.warning(
                "embedding_cache_serialize_failed",
                extra={"hash": content_hash[:8], "error": str(exc)},
            )
            return False

        values: list[float] = (
            embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        )

        value = {
            "embedding": embedding_b64,
            "dimensions": len(values),
            "model": model_name,
        }

        ttl = self._cfg.redis.embedding_cache_ttl_seconds
        success = await self._cache.set_json(
            value=value,
            ttl_seconds=ttl,
            parts=("embed", "v1", model_name, content_hash),
        )

        if success:
            logger.debug(
                "embedding_cached",
                extra={
                    "model": model_name,
                    "hash": content_hash[:8],
                    "dimensions": len(values),
                    "ttl": ttl,
                },
            )
        return success

    async def get_or_compute(
        self,
        text: str,
        model_name: str,
        compute_fn: Any,
    ) -> list[float]:
        """Get cached embedding or compute and cache it.

        This is a convenience method that handles the cache-aside pattern.

        Args:
            text: Text to embed.
            model_name: Embedding model name.
            compute_fn: Async function that computes the embedding.
                       Should accept (text) and return numpy array or list[float].

        Returns:
            Embedding as list of floats.
        """
        content_hash = self.hash_content(text)

        # Try cache first
        cached = await self.get(content_hash, model_name)
        if cached is not None:
            return cached

        # Compute embedding
        embedding = await compute_fn(text)

        # Cache the result (async, non-blocking)
        await self.set(content_hash, model_name, embedding)

        # Return as list
        if hasattr(embedding, "tolist"):
            return embedding.tolist()
        return list(embedding)
