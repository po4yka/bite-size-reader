from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_upgrade_preserves_full_metadata_when_upserting(monkeypatch) -> None:
    migration = importlib.import_module(
        "app.cli.migrations.004_migrate_summary_embeddings_to_chroma"
    )

    captured: dict[str, object] = {}

    class _FakeEmbeddingService:
        def deserialize_embedding(self, _blob: bytes) -> list[float]:
            return [0.1, 0.2, 0.3]

    class _FakeStore:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs

        def upsert_notes(
            self,
            vectors: list[list[float]],
            metadatas: list[dict[str, object]],
        ) -> None:
            captured["vectors"] = vectors
            captured["metadatas"] = metadatas

    cfg = SimpleNamespace(
        host="http://localhost:8000",
        auth_token=None,
        environment="test",
        user_scope="scope",
        collection_version="v2",
        required=True,
        connection_timeout=4.25,
    )

    metadata = {
        "request_id": 11,
        "summary_id": 22,
        "user_id": 33,
        "language": "en",
        "tags": ["ai", "ml"],
        "topics": ["ai"],
        "text": "Semantic note text",
        "title": "Article title",
        "environment": "test",
        "user_scope": "scope",
    }

    monkeypatch.setattr(
        migration,
        "load_config",
        lambda allow_stub_telegram=True: SimpleNamespace(vector_store=cfg),
    )
    monkeypatch.setattr(migration, "create_embedding_service", lambda: _FakeEmbeddingService())
    monkeypatch.setattr(migration, "ChromaVectorStore", _FakeStore)
    monkeypatch.setattr(migration, "_log_chroma_heartbeat", lambda _store: None)
    monkeypatch.setattr(migration, "_log_query_probe", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        migration,
        "_fetch_summary_embeddings",
        lambda _db, environment, user_scope: [
            {
                "request_id": 11,
                "summary_id": 22,
                "embedding_blob": b"blob",
                "metadata": metadata,
            }
        ],
    )

    migration.upgrade(MagicMock())

    assert captured["vectors"] == [[0.1, 0.2, 0.3]]
    assert captured["metadatas"] == [metadata]
    assert captured["init_kwargs"] == {
        "host": "http://localhost:8000",
        "auth_token": None,
        "environment": "test",
        "user_scope": "scope",
        "collection_version": "v2",
        "required": True,
        "connection_timeout": 4.25,
    }
