"""Focused tests for repository embedding persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.infrastructure.embedding.repository_embedding import RepositoryEmbeddingGenerator


@pytest.mark.asyncio
async def test_upsert_db_row_returns_insert_returning_row_without_extra_read() -> None:
    returned_row = MagicMock()
    returned_row.id = 123

    result = MagicMock()
    result.scalar_one.return_value = returned_row

    executed_statements = []
    mock_session = AsyncMock()

    async def execute(stmt):
        executed_statements.append(stmt)
        return result

    mock_session.execute = AsyncMock(side_effect=execute)

    transaction_ctx = MagicMock()

    async def _aenter(self):
        return mock_session

    async def _aexit(self, *args):
        pass

    transaction_ctx.__aenter__ = _aenter
    transaction_ctx.__aexit__ = _aexit

    db = MagicMock()
    db.transaction.return_value = transaction_ctx

    generator = RepositoryEmbeddingGenerator(
        embedding_service=MagicMock(),
        qdrant_store=None,
        db=db,
        environment="test",
        user_scope="default",
    )

    actual = await generator._upsert_db_row(
        repository_id=7,
        model_name="model",
        model_version="1.0",
        embedding_blob=b"blob",
        dimensions=3,
        language=None,
    )

    assert actual is returned_row
    db.transaction.assert_called_once_with()
    db.session.assert_not_called()

    compiled = str(
        executed_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ON CONFLICT" in compiled
    assert "RETURNING repository_embeddings.id" in compiled
    assert "repository_embeddings.repository_id" in compiled
