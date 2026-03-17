"""Protocol definition for embedding service providers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
