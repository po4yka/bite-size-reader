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
    fake_db = MagicMock()
    fake_db.dispose = AsyncMock()
    monkeypatch.setattr(backfill_embeddings, "DatabaseConfig", lambda dsn=None: MagicMock())
    monkeypatch.setattr(backfill_embeddings, "Database", lambda config: fake_db)
    monkeypatch.setattr(backfill_embeddings, "create_embedding_service", lambda cfg: MagicMock())
    monkeypatch.setattr(
        backfill_embeddings,
        "SummaryEmbeddingGenerator",
        lambda **_kwargs: fake_generator,
    )

    async def fake_fetch(db, *, limit=None, force=False):
        assert db is fake_db
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

    await backfill_embeddings.backfill_embeddings("postgresql+asyncpg://test", limit=5, force=True)

    assert fetch_calls == [{"limit": 5, "force": True}]
    fake_db.dispose.assert_awaited_once()
    fake_generator.generate_embedding_for_summary.assert_awaited_once_with(
        summary_id=11,
        payload={"summary_250": "Summary text"},
        language="en",
        force=True,
    )


def test_main_returns_zero_for_help(monkeypatch, capsys) -> None:
    monkeypatch.setattr(backfill_embeddings.sys, "argv", ["backfill_embeddings.py", "--help"])

    assert backfill_embeddings.main() == 0
    assert "--dsn=DSN" in capsys.readouterr().out


def test_main_rejects_legacy_db_option(monkeypatch) -> None:
    monkeypatch.setattr(
        backfill_embeddings.sys,
        "argv",
        ["backfill_embeddings.py", "--db=/tmp/ratatoskr.db"],
    )

    assert backfill_embeddings.main() == 1
