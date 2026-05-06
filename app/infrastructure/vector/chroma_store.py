"""Stub: retained only so historical migration modules can be imported by Alembic.

The active vector backend is QdrantVectorStore (app/infrastructure/vector/qdrant_store.py).
This file must not be deleted while the legacy SQLite Alembic revisions under
app/db/alembic/versions/_legacy_sqlite/ exist.
"""

from __future__ import annotations

from typing import Any


class ChromaVectorStore:
    """Stub: satisfies the import in 004_migrate_summary_embeddings_to_chroma.py only."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def upsert_notes(self, vectors: list[list[float]], metadatas: list[dict[str, Any]]) -> None:
        pass

    def query(
        self, vector: list[float], where: dict[str, Any], n_results: int = 10
    ) -> dict[str, Any]:
        return {}
