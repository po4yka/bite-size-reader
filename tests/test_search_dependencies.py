import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

mock_chromadb = MagicMock()
mock_chromadb.errors.ChromaError = Exception
sys.modules["chromadb"] = mock_chromadb
sys.modules["chromadb.errors"] = mock_chromadb.errors

from app.api.dependencies import search_resources


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


def test_default_vector_store_factory_forwards_required_and_timeout() -> None:
    cfg = SimpleNamespace(
        host="http://localhost:8000",
        auth_token="token",
        environment="test",
        user_scope="scope",
        collection_version="v9",
        required=True,
        connection_timeout=3.5,
    )

    with patch.object(search_resources, "ChromaVectorStore", autospec=True) as store_cls:
        store = object()
        store_cls.return_value = store

        created = search_resources._default_vector_store_factory(cfg)  # type: ignore[arg-type]

    assert created is store
    store_cls.assert_called_once_with(
        host="http://localhost:8000",
        auth_token="token",
        environment="test",
        user_scope="scope",
        collection_version="v9",
        required=True,
        connection_timeout=3.5,
    )
