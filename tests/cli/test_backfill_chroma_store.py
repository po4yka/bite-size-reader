from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.cli import backfill_chroma_store
from app.config import ChromaConfig


def test_load_chroma_config_preserves_runtime_flags(monkeypatch) -> None:
    base_cfg = SimpleNamespace(
        host="http://env-host:8000",
        auth_token="env-token",
        environment="env",
        user_scope="scope",
        collection_version="v9",
        required=True,
        connection_timeout=4.25,
    )

    monkeypatch.setattr(
        backfill_chroma_store,
        "load_config",
        lambda allow_stub_telegram=True: SimpleNamespace(vector_store=base_cfg),
    )

    cfg = backfill_chroma_store._load_chroma_config(
        host="http://cli-host:8000",
        auth_token=None,
        environment=None,
        user_scope=None,
        collection_version=None,
    )

    assert cfg.host == "http://cli-host:8000"
    assert cfg.auth_token == "env-token"
    assert cfg.environment == "env"
    assert cfg.user_scope == "scope"
    assert cfg.collection_version == "v9"
    assert cfg.required is True
    assert cfg.connection_timeout == 4.25


@pytest.mark.asyncio
async def test_backfill_replaces_request_vectors(monkeypatch) -> None:
    fake_db = MagicMock()
    fake_repo = MagicMock()
    fake_repo.async_get_summary_embedding = MagicMock(return_value=None)

    async def fake_get_embedding(summary_id: int) -> dict[str, object] | None:
        if summary_id != 22:
            return None
        return {"embedding_blob": b"blob"}

    fake_repo.async_get_summary_embedding = fake_get_embedding

    class FakeGenerator:
        def __init__(self, **_kwargs) -> None:
            self.generate_embedding_for_summary = MagicMock()

    class FakeEmbeddingService:
        def deserialize_embedding(self, _blob: bytes) -> list[float]:
            return [0.1, 0.2, 0.3]

    fake_store = MagicMock()
    fake_store.replace_request_notes = MagicMock()

    summary = {
        "id": 22,
        "request_id": 11,
        "lang": "en",
        "json_payload": {"summary_250": "Short summary", "metadata": {"title": "Title"}},
        "request": {"user_id": 33},
    }

    monkeypatch.setattr(
        backfill_chroma_store,
        "load_config",
        lambda allow_stub_telegram=True: SimpleNamespace(
            embedding=SimpleNamespace(max_token_length=512),
            vector_store=SimpleNamespace(
                host="http://localhost:8000",
                auth_token=None,
                environment="dev",
                user_scope="public",
                collection_version="v1",
                required=False,
                connection_timeout=10.0,
            ),
        ),
    )
    monkeypatch.setattr(backfill_chroma_store, "DatabaseSessionManager", lambda path: fake_db)
    monkeypatch.setattr(
        backfill_chroma_store, "SqliteEmbeddingRepositoryAdapter", lambda db: fake_repo
    )
    monkeypatch.setattr(
        backfill_chroma_store, "create_embedding_service", lambda cfg: FakeEmbeddingService()
    )
    monkeypatch.setattr(backfill_chroma_store, "SummaryEmbeddingGenerator", FakeGenerator)
    monkeypatch.setattr(backfill_chroma_store, "_fetch_summaries", lambda db, limit: [summary])
    monkeypatch.setattr(backfill_chroma_store, "ChromaVectorStore", lambda **_kwargs: fake_store)
    monkeypatch.setattr(
        backfill_chroma_store.MetadataBuilder,
        "prepare_chunk_windows_for_upsert",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        backfill_chroma_store.MetadataBuilder,
        "prepare_for_upsert",
        lambda **_kwargs: (
            "Short summary",
            {"request_id": 11, "summary_id": 22, "text": "Short summary"},
        ),
    )

    await backfill_chroma_store.backfill_chroma_store(
        "/tmp/app.db",
        ChromaConfig(
            host="http://localhost:8000",
            auth_token=None,
            environment="dev",
            user_scope="public",
            collection_version="v1",
            required=False,
            connection_timeout=10.0,
        ),
        batch_size=1,
    )

    fake_store.replace_request_notes.assert_called_once_with(
        11,
        [[0.1, 0.2, 0.3]],
        [{"request_id": 11, "summary_id": 22, "text": "Short summary"}],
    )
