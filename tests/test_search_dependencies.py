import sys
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

mock_chromadb = MagicMock()
mock_chromadb.errors.ChromaError = Exception
sys.modules["chromadb"] = mock_chromadb
sys.modules["chromadb.errors"] = mock_chromadb.errors

from app.api.dependencies import search_resources
from app.di import search as search_di


class DummyEmbeddingService:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.close()


class DummyVectorStore:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.close()


@pytest.mark.asyncio
async def test_chroma_resource_manager_reuses_singleton_and_shuts_down():
    search_resources.set_chroma_factories_for_tests(
        embedding_factory=DummyEmbeddingService,
        vector_store_factory=lambda config: DummyVectorStore(),
        config_factory=lambda: SimpleNamespace(
            host="http://localhost",
            auth_token=None,
            environment="test",
            user_scope="user",
            collection_version="v1",
        ),
    )

    try:
        first = await search_resources.get_chroma_search_service()
        second = await search_resources.get_chroma_search_service()

        assert first is second

        embedding = getattr(first, "_embedding_service", None)
        vector_store = getattr(first, "_vector_store", None)

        await search_resources.shutdown_chroma_search_resources()

        assert embedding.closed is True
        assert vector_store.closed is True

        fresh = await search_resources.get_chroma_search_service()
        assert fresh is not first
    finally:
        search_resources.set_chroma_factories_for_tests()
        await search_resources.shutdown_chroma_search_resources()


@pytest.mark.asyncio
async def test_chroma_resource_test_factories_build_service_without_api_runtime():
    search_resources.set_chroma_factories_for_tests(
        embedding_factory=DummyEmbeddingService,
        vector_store_factory=lambda config: DummyVectorStore(),
        config_factory=lambda: SimpleNamespace(host="http://localhost"),
    )

    try:
        service = await search_resources.get_chroma_search_service()
        assert getattr(service, "_embedding_service", None) is not None
        assert getattr(service, "_vector_store", None) is not None
    finally:
        search_resources.set_chroma_factories_for_tests()
        await search_resources.shutdown_chroma_search_resources()


def test_build_search_dependencies_raises_when_chroma_is_required(monkeypatch) -> None:
    class FailingStore:
        def __init__(self, **_kwargs) -> None:
            raise RuntimeError("chroma down")

    monkeypatch.setattr(
        "app.infrastructure.vector.chroma_store.ChromaVectorStore",
        FailingStore,
    )

    cfg = SimpleNamespace(
        runtime=SimpleNamespace(topic_search_max_results=5, request_timeout_sec=5.0),
        vector_store=SimpleNamespace(
            host="http://localhost:8000",
            auth_token=None,
            environment="test",
            user_scope="public",
            collection_version="v1",
            required=True,
            connection_timeout=3.0,
        ),
        embedding=SimpleNamespace(provider="local", max_token_length=512),
    )

    with pytest.raises(RuntimeError, match="chroma down"):
        search_di.build_search_dependencies(
            cast("Any", cfg),
            db=MagicMock(),
            llm_client=MagicMock(),
            audit_func=lambda *_args, **_kwargs: None,
        )
