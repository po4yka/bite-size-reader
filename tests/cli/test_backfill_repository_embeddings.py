"""Tests for app.cli.backfill_repository_embeddings."""

from __future__ import annotations

import types
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.cli import backfill_repository_embeddings as cli_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    repo_id: int,
    user_id: int = 1,
    full_name: str | None = None,
    analysis_json: dict | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.id = repo_id
    repo.user_id = user_id
    repo.full_name = full_name or f"owner/repo-{repo_id}"
    repo.description = None
    repo.primary_language = None
    repo.languages_json = {}
    repo.topics_json = []
    repo.readme_excerpt = None
    repo.analysis_json = analysis_json
    return repo


def _make_embedding(repo_id: int, model_version: str = "1.0") -> MagicMock:
    emb = MagicMock()
    emb.id = repo_id * 100
    emb.repository_id = repo_id
    emb.model_version = model_version
    return emb


def _make_db_with_rows(
    row_batches: list[list[tuple[MagicMock, MagicMock | None]]],
) -> MagicMock:
    """Build a fake Database whose session() returns batches in order."""
    batch_iter = iter(row_batches)

    mock_db = MagicMock()
    mock_db.dispose = AsyncMock()
    mock_db.executed_statements = []

    def session_ctx():
        ctx = MagicMock()

        async def _aenter(self):
            mock_session = AsyncMock()

            async def execute(stmt):
                mock_db.executed_statements.append(stmt)
                try:
                    batch = next(batch_iter)
                except StopIteration:
                    batch = []
                result = MagicMock()
                result.all.return_value = batch
                return result

            mock_session.execute = AsyncMock(side_effect=execute)
            return mock_session

        async def _aexit(self, *args):
            pass

        ctx.__aenter__ = _aenter
        ctx.__aexit__ = _aexit
        return ctx

    mock_db.session = session_ctx
    return mock_db


def _compile_stmt(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _make_mutating_db_with_missing_rows(
    repos: list[MagicMock],
) -> MagicMock:
    """Fake DB that evaluates the backfill query against changing eligibility.

    Once a repository is marked embedded, it no longer matches the missing-embedding
    filter. This exposes OFFSET pagination skipping rows after earlier rows are
    processed out of the WHERE result set.
    """
    embedded_repo_ids: set[int] = set()

    mock_db = MagicMock()
    mock_db.dispose = AsyncMock()
    mock_db.executed_statements = []
    mock_db.mark_embedded = lambda repo_id: embedded_repo_ids.add(repo_id)

    def session_ctx():
        ctx = MagicMock()

        async def _aenter(self):
            mock_session = AsyncMock()

            async def execute(stmt):
                mock_db.executed_statements.append(stmt)
                sql = _compile_stmt(stmt)
                cursor_match = re.search(r"repositories\.id > (\d+)", sql)
                last_seen_id = int(cursor_match.group(1)) if cursor_match else 0
                limit_match = re.search(r"LIMIT (\d+)", sql)
                limit = int(limit_match.group(1)) if limit_match else len(repos)
                offset_match = re.search(r"OFFSET (\d+)", sql)
                offset = int(offset_match.group(1)) if offset_match else 0

                eligible = [
                    (repo, None)
                    for repo in repos
                    if repo.id > last_seen_id and repo.id not in embedded_repo_ids
                ]
                batch = eligible[offset : offset + limit]
                result = MagicMock()
                result.all.return_value = batch
                return result

            mock_session.execute = AsyncMock(side_effect=execute)
            return mock_session

        async def _aexit(self, *args):
            pass

        ctx.__aenter__ = _aenter
        ctx.__aexit__ = _aexit
        return ctx

    mock_db.session = session_ctx
    return mock_db


def _ensure_qdrant_stub() -> None:
    """Inject a fake qdrant_store module so tests don't need qdrant_client installed.

    The CLI does a lazy ``from app.infrastructure.vector.qdrant_store import
    QdrantVectorStore`` inside the async function body. We pre-populate
    sys.modules so that import resolves without the real qdrant_client package.
    """
    import sys

    qs_key = "app.infrastructure.vector.qdrant_store"
    if qs_key not in sys.modules or not hasattr(sys.modules[qs_key], "QdrantVectorStore"):
        stub = types.ModuleType(qs_key)
        stub.QdrantVectorStore = MagicMock()  # type: ignore[attr-defined]
        sys.modules[qs_key] = stub


def _patch_infra(monkeypatch, mock_db, embedding_gen):
    """Monkeypatch load_config, Database, embedding service, qdrant, and generator."""
    _ensure_qdrant_stub()

    fake_cfg = types.SimpleNamespace(
        embedding=types.SimpleNamespace(
            provider="local",
            max_token_length=512,
            embedding_dim=768,
        ),
        vector_store=types.SimpleNamespace(
            url="http://localhost:6333",
            api_key=None,
            environment="test",
            user_scope="default",
            collection_version="v1",
            required=False,
            connection_timeout=5,
        ),
    )
    monkeypatch.setattr(cli_mod, "load_config", lambda allow_stub_telegram=True: fake_cfg)
    monkeypatch.setattr(cli_mod, "DatabaseConfig", lambda dsn=None: MagicMock())
    monkeypatch.setattr(cli_mod, "Database", lambda config: mock_db)
    monkeypatch.setattr(cli_mod, "create_embedding_service", lambda cfg: MagicMock())
    monkeypatch.setattr(
        cli_mod,
        "resolve_embedding_space_identifier",
        lambda cfg: "test-space",
    )
    monkeypatch.setattr(
        cli_mod,
        "RepositoryEmbeddingGenerator",
        lambda **_kw: embedding_gen,
    )


# ---------------------------------------------------------------------------
# Stub generator
# ---------------------------------------------------------------------------


class StubEmbeddingGenerator:
    """Records calls; optionally raises on a specific repository_id."""

    def __init__(self, raise_on_id: int | None = None, on_success=None) -> None:
        self.calls: list[int] = []
        self._raise_on_id = raise_on_id
        self._on_success = on_success

    async def regenerate(self, repository, *, analysis, correlation_id):
        self.calls.append(repository.id)
        if self._raise_on_id is not None and repository.id == self._raise_on_id:
            raise RuntimeError(f"Forced error for repo {repository.id}")
        if self._on_success is not None:
            self._on_success(repository.id)
        result = MagicMock()
        result.id = repository.id * 100
        return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run: 3 repos missing embeddings → no regenerate calls, would_create=3."""
    repos = [_make_repo(i) for i in range(1, 4)]
    rows: list[tuple[MagicMock, MagicMock | None]] = [(r, None) for r in repos]

    gen = StubEmbeddingGenerator()
    db = _make_db_with_rows([rows, []])  # second batch empty → stop
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=True)

    assert gen.calls == [], "no regenerate calls in dry-run"
    assert summary["would_create"] == 3
    assert summary["embeddings_created"] == 0
    assert summary["embeddings_refreshed"] == 0
    assert summary["dry_run"] is True
    db.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_creates_missing_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """3 repos with no embeddings → 3 regenerate calls, embeddings_created=3."""
    repos = [_make_repo(i) for i in range(1, 4)]
    rows: list[tuple[MagicMock, MagicMock | None]] = [(r, None) for r in repos]

    gen = StubEmbeddingGenerator()
    db = _make_db_with_rows([rows, []])
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False)

    assert sorted(gen.calls) == [1, 2, 3]
    assert summary["embeddings_created"] == 3
    assert summary["embeddings_refreshed"] == 0
    assert summary["errors"] == 0
    assert summary["processed"] == 3


@pytest.mark.asyncio
async def test_backfill_uses_keyset_pagination_when_rows_stop_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Processing earlier rows must not skip later rows that still need embeddings."""
    repos = [_make_repo(i) for i in range(1, 5)]

    db = _make_mutating_db_with_missing_rows(repos)
    gen = StubEmbeddingGenerator(on_success=db.mark_embedded)
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False, batch_size=2)

    assert gen.calls == [1, 2, 3, 4]
    assert summary["processed"] == 4
    assert summary["embeddings_created"] == 4
    compiled_statements = [_compile_stmt(stmt) for stmt in db.executed_statements]
    assert all(" OFFSET " not in sql for sql in compiled_statements)
    assert "repositories.id > 0" in compiled_statements[0]
    assert "repositories.id > 2" in compiled_statements[1]


@pytest.mark.asyncio
async def test_skips_when_embedding_present_and_no_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repos with existing embeddings and no --model-version-target → 0 writes.

    When model_version_target is None the WHERE clause filters to IS NULL only,
    so the DB returns an empty batch and the generator is never called.
    """
    gen = StubEmbeddingGenerator()
    # All repos already have embeddings → the WHERE (IS NULL) returns nothing
    db = _make_db_with_rows([[]])  # first batch already empty
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False, model_version_target=None)

    assert gen.calls == []
    assert summary["embeddings_created"] == 0
    assert summary["embeddings_refreshed"] == 0
    assert summary["processed"] == 0


@pytest.mark.asyncio
async def test_refreshes_when_model_version_target_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repos with model_version='1.0', target='2.0' → 3 refreshed."""
    repos = [_make_repo(i) for i in range(1, 4)]
    embeddings = [_make_embedding(r.id, model_version="1.0") for r in repos]
    rows = list(zip(repos, embeddings, strict=False))

    gen = StubEmbeddingGenerator()
    db = _make_db_with_rows([rows, []])
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(
        dry_run=False, model_version_target="2.0"
    )

    assert sorted(gen.calls) == [1, 2, 3]
    assert summary["embeddings_refreshed"] == 3
    assert summary["embeddings_created"] == 0
    assert summary["errors"] == 0


@pytest.mark.asyncio
async def test_user_id_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only repos for user_id=2 are returned (WHERE clause enforced by DB mock)."""
    user_b_repos = [_make_repo(i, user_id=2) for i in range(10, 13)]
    rows: list[tuple[MagicMock, MagicMock | None]] = [(r, None) for r in user_b_repos]

    gen = StubEmbeddingGenerator()
    db = _make_db_with_rows([rows, []])
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False, user_id=2)

    assert summary["processed"] == 3
    assert summary["embeddings_created"] == 3


@pytest.mark.asyncio
async def test_idempotent_second_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second run with same args returns 0 writes (DB returns empty batch)."""
    gen = StubEmbeddingGenerator()
    # Simulate: after first run all embeddings exist → query returns nothing
    db = _make_db_with_rows([[]])
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False)

    assert gen.calls == []
    assert summary["embeddings_created"] == 0
    assert summary["embeddings_refreshed"] == 0
    assert summary["processed"] == 0


@pytest.mark.asyncio
async def test_error_in_one_row_does_not_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generator raises on repo 2 → rows 1 and 3 still processed; errors=1."""
    repos = [_make_repo(i) for i in [1, 2, 3]]
    rows: list[tuple[MagicMock, MagicMock | None]] = [(r, None) for r in repos]

    gen = StubEmbeddingGenerator(raise_on_id=2)
    db = _make_db_with_rows([rows, []])
    _patch_infra(monkeypatch, db, gen)

    summary = await cli_mod.backfill_repository_embeddings(dry_run=False)

    assert 1 in gen.calls
    assert 2 in gen.calls
    assert 3 in gen.calls
    assert summary["errors"] == 1
    assert summary["embeddings_created"] == 2
    assert summary["processed"] == 3


# ---------------------------------------------------------------------------
# main() smoke tests
# ---------------------------------------------------------------------------


def test_main_help(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(cli_mod.sys, "argv", ["prog", "--help"])
    assert cli_mod.main() == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--batch-size" in out


def test_main_invalid_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mod.sys, "argv", ["prog", "--batch-size=abc"])
    assert cli_mod.main() == 1


def test_main_unknown_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mod.sys, "argv", ["prog", "--unknown-flag"])
    assert cli_mod.main() == 1
