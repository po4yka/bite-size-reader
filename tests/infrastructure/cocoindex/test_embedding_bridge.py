"""Tests for the CocoIndex embedding bridge.

Tests the synchronous wrapper around the async embedding service.
Does not require a running CocoIndex instance.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeEmbeddingService:
    """Minimal fake embedding service for bridge tests."""

    def __init__(self, return_vector: list[float] | None = None) -> None:
        self._vector = return_vector or [0.1, 0.2, 0.3]
        self.call_count = 0

    async def generate_embedding(
        self, text: str, *, language: str | None = None, task_type: str | None = None
    ) -> list[float]:
        self.call_count += 1
        return list(self._vector)

    def get_model_name(self, language: str | None = None) -> str:
        return "fake-model"

    def get_dimensions(self, language: str | None = None) -> int:
        return len(self._vector)

    def serialize_embedding(self, embedding: Any) -> bytes:
        return b""

    def deserialize_embedding(self, blob: bytes) -> list[float]:
        return list(self._vector)

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass


def _reset_bridge_globals() -> None:
    """Reset bridge module globals between tests."""
    import app.infrastructure.cocoindex.embedding_bridge as bridge

    bridge._loop = None
    bridge._loop_thread = None
    bridge._service = None


@pytest.fixture(autouse=True)
def reset_bridge() -> Generator[None, None, None]:
    _reset_bridge_globals()
    yield
    _reset_bridge_globals()


def test_embed_text_sync_returns_vector() -> None:
    fake_service = _FakeEmbeddingService([0.1, 0.2, 0.3])

    with (
        patch("app.config.load_config"),
        patch(
            "app.infrastructure.embedding.embedding_factory.create_embedding_service",
            return_value=fake_service,
        ),
    ):
        from app.infrastructure.cocoindex.embedding_bridge import embed_text_sync

        result = embed_text_sync("hello world")

    assert isinstance(result, list)
    assert len(result) == 3
    assert result == pytest.approx([0.1, 0.2, 0.3])


def test_embed_text_sync_passes_language() -> None:
    received_language: list[str | None] = []

    class _LangCapture(_FakeEmbeddingService):
        async def generate_embedding(
            self, text: str, *, language: str | None = None, task_type: str | None = None
        ) -> list[float]:
            received_language.append(language)
            return [0.0]

    fake_service = _LangCapture()

    with (
        patch("app.config.load_config"),
        patch(
            "app.infrastructure.embedding.embedding_factory.create_embedding_service",
            return_value=fake_service,
        ),
    ):
        from app.infrastructure.cocoindex.embedding_bridge import embed_text_sync

        embed_text_sync("hello", language="ru")

    assert received_language == ["ru"]


def test_embed_text_sync_singleton_service() -> None:
    fake_service = _FakeEmbeddingService()
    create_calls: list[int] = []

    def _factory(_cfg: Any) -> _FakeEmbeddingService:
        create_calls.append(1)
        return fake_service

    with (
        patch("app.config.load_config"),
        patch(
            "app.infrastructure.embedding.embedding_factory.create_embedding_service",
            side_effect=_factory,
        ),
    ):
        from app.infrastructure.cocoindex.embedding_bridge import embed_text_sync

        embed_text_sync("first call")
        embed_text_sync("second call")

    assert len(create_calls) == 1, "Embedding service must be created only once (singleton)"
    assert fake_service.call_count == 2
