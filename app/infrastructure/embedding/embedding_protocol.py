"""Protocol definition for embedding service providers."""

from __future__ import annotations

import struct
from typing import Any, Protocol, runtime_checkable


def pack_embedding(embedding: Any) -> bytes:
    """Serialize an embedding vector as packed float32 bytes for DB storage.

    Accepts numpy arrays or list[float]. Uses struct packing instead of pickle
    to avoid deserialization attack vectors if the DB is compromised.
    """
    values: list[float] = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return struct.pack(f"<{len(values)}f", *values)


def unpack_embedding(blob: bytes) -> list[float]:
    """Deserialize an embedding vector from DB storage.

    Supports both the current struct-packed format and the legacy pickle format
    for backward compatibility with existing stored embeddings.
    """
    try:
        count = len(blob) // 4  # 4 bytes per float32
        return list(struct.unpack(f"<{count}f", blob))
    except struct.error:
        import pickle

        return pickle.loads(blob)  # nosec B301


class EmbeddingSerializationMixin:
    """Default serialize/deserialize implementations shared by all embedding providers."""

    def serialize_embedding(self, embedding: Any) -> bytes:
        return pack_embedding(embedding)

    def deserialize_embedding(self, blob: bytes) -> list[float]:
        return unpack_embedding(blob)


@runtime_checkable
class EmbeddingServiceProtocol(Protocol):
    """Interface that all embedding providers must satisfy."""

    async def generate_embedding(
        self, text: str, *, language: str | None = None, task_type: str | None = None
    ) -> Any: ...

    def serialize_embedding(self, embedding: Any) -> bytes: ...

    def deserialize_embedding(self, blob: bytes) -> list[float]: ...

    def get_model_name(self, language: str | None = None) -> str: ...

    def get_dimensions(self, language: str | None = None) -> int: ...

    def close(self) -> None: ...

    async def aclose(self) -> None: ...
