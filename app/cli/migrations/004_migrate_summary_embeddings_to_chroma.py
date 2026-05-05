"""No-op migration: ChromaDB backend replaced by Qdrant.

This migration originally streamed embeddings into a ChromaDB collection.
The ChromaDB backend has been removed; embeddings are now indexed via Qdrant.
Use ``python -m app.cli.backfill_vector_store`` to (re-)index embeddings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def upgrade(db: DatabaseSessionManager) -> None:
    """No-op: vector backend was migrated from ChromaDB to Qdrant."""
    logger.info(
        "Skipping migration 004: ChromaDB backend replaced by Qdrant. "
        "Use the Qdrant backfill CLI to re-index embeddings."
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """No-op rollback placeholder."""
    logger.info("Migration 004 rollback is a no-op.")
