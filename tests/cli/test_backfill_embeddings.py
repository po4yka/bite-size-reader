from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cli import backfill_embeddings


@pytest.mark.asyncio
async def test_backfill_embeddings_force_fetches_existing_embeddings(monkeypatch) -> None:
    fetch_calls: list[dict[str, object]] = []

    class FakeGenerator:
        def __init__(self, **_kwargs) -> None:
            self.generate_embedding_for_summary = AsyncMock(return_value=True)

    fake_generator = FakeGenerator()

    monkeypatch.setattr(
        backfill_embeddings,
        "load_config",
        lambda allow_stub_telegram=True: SimpleNamespace(
            embedding=SimpleNamespace(provider="gemini", max_token_length=1024)
        ),
    )
    monkeypatch.setattr(backfill_embeddings, "DatabaseSessionManager", lambda path: MagicMock())
    monkeypatch.setattr(backfill_embeddings, "create_embedding_service", lambda cfg: MagicMock())
    monkeypatch.setattr(
        backfill_embeddings,
        "SummaryEmbeddingGenerator",
        lambda **_kwargs: fake_generator,
    )

    def fake_fetch(db, *, limit=None, force=False):
        fetch_calls.append({"limit": limit, "force": force})
        return [
            {
                "id": 11,
                "request_id": 22,
                "json_payload": {"summary_250": "Summary text"},
                "language": "en",
            }
        ]

    monkeypatch.setattr(backfill_embeddings, "get_summaries_for_embedding_backfill", fake_fetch)

    await backfill_embeddings.backfill_embeddings("/tmp/app.db", limit=5, force=True)

    assert fetch_calls == [{"limit": 5, "force": True}]
    fake_generator.generate_embedding_for_summary.assert_awaited_once_with(
        summary_id=11,
        payload={"summary_250": "Summary text"},
        language="en",
        force=True,
    )
