from __future__ import annotations

import peewee
import pytest

from app.db.models import LLMCall, Request, database_proxy
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)


@pytest.fixture
def in_memory_db(tmp_path):
    old_db = database_proxy.obj
    db_path = str(tmp_path / "test_llm_repository_batch.db")
    db = peewee.SqliteDatabase(db_path, pragmas={"journal_mode": "wal"})
    database_proxy.initialize(db)
    db.bind([Request, LLMCall], bind_refs=False, bind_backrefs=False)
    db.create_tables([Request, LLMCall])
    yield db
    db.drop_tables([Request, LLMCall])
    db.close()
    database_proxy.initialize(old_db)
    for model in [Request, LLMCall]:
        model._meta.database = database_proxy


@pytest.mark.asyncio
async def test_insert_llm_calls_batch_persists_all_rows(in_memory_db) -> None:
    request = Request.create(
        type="url",
        status="processing",
        correlation_id="cid-llm-batch",
        user_id=1,
        input_url="https://example.com/llm-batch",
        normalized_url="https://example.com/llm-batch",
        dedupe_hash="hash-llm-batch",
    )
    repo = SqliteLLMRepositoryAdapter(database_proxy)

    inserted_ids = await repo.async_insert_llm_calls_batch(
        [
            {
                "request_id": request.id,
                "provider": "openrouter",
                "model": "model-a",
                "status": "ok",
                "response_text": "first",
            },
            {
                "request_id": request.id,
                "provider": "openrouter",
                "model": "model-b",
                "status": "error",
                "error_text": "failed",
                "response_text": "",
            },
        ]
    )

    rows = list(LLMCall.select().where(LLMCall.request == request.id).order_by(LLMCall.id))

    assert len(inserted_ids) == 2
    assert [row.id for row in rows] == inserted_ids
    assert rows[0].model == "model-a"
    assert rows[1].status == "error"
