"""Stub: retained only so historical migration modules can be imported by Alembic.

The active vector backend is QdrantVectorStore (app/infrastructure/vector/qdrant_store.py).
This file must not be deleted while app/cli/migrations/004_migrate_summary_embeddings_to_chroma.py
and app/db/alembic/versions/0005_004_migrate_summary_embeddings_to_chroma.py exist.
"""

from __future__ import annotations


class ChromaVectorStore:
    """Stub: satisfies the import in 004_migrate_summary_embeddings_to_chroma.py only."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass
