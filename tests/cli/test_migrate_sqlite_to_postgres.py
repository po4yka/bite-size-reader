"""Unit tests for migrate_sqlite_to_postgres.

Tests 1-2 run on synthetic in-memory SQLite only (no Postgres needed).
Test 3 (bytes round-trip) and Test 4 (dry-run) require TEST_DATABASE_URL and
are skipped when it is not set.
"""

from __future__ import annotations

import os
from typing import Any
import peewee
import pytest

from app.cli._legacy_peewee_models import ALL_MODELS
from app.cli._legacy_peewee_models._base import database_proxy
from app.cli.migrate_sqlite_to_postgres import (
    _chunked,
    _is_json_column,
    _legacy_row_to_dict,
    _resolve_sa_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set — skipping Postgres-gated test",
)


def _init_in_memory_legacy_db() -> peewee.SqliteDatabase:
    """Create an in-memory SQLite and bind all legacy models to it."""
    mem_db = peewee.SqliteDatabase(":memory:")
    database_proxy.initialize(mem_db)
    return mem_db


# ---------------------------------------------------------------------------
# Test 1: per-row JSON coercion
# ---------------------------------------------------------------------------


def test_json_coercion_parses_stringified_json() -> None:
    """_legacy_row_to_dict normalises a stringified-JSON column into a dict."""
    # Build a tiny synthetic Peewee model with a JSON field
    import playhouse.sqlite_ext as psql_ext

    mem_db = _init_in_memory_legacy_db()

    class _TinyModel(peewee.Model):
        id = peewee.AutoField()
        payload = psql_ext.JSONField(null=True)

        class Meta:
            database = mem_db
            table_name = "tiny_model"

    mem_db.create_tables([_TinyModel])
    row = _TinyModel.create(payload={"key": "value"})

    # Build a minimal SA model stub with a JSONB column
    from sqlalchemy import Column, Integer
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
    from sqlalchemy.orm import DeclarativeBase

    class _Base(DeclarativeBase):
        pass

    class _TinySA(_Base):
        __tablename__ = "tiny_model"
        id: Any = Column(Integer, primary_key=True)
        payload: Any = Column(PG_JSONB, nullable=True)

    result = _legacy_row_to_dict(_TinyModel, row, _TinySA)
    assert result["payload"] == {"key": "value"}
    assert "id" in result


def test_json_coercion_handles_stringified_text() -> None:
    """_legacy_row_to_dict wraps invalid-JSON text in __legacy_text__ sentinel."""
    import playhouse.sqlite_ext as psql_ext

    mem_db = _init_in_memory_legacy_db()

    class _TinyModel2(peewee.Model):
        id = peewee.AutoField()
        payload = psql_ext.JSONField(null=True)

        class Meta:
            database = mem_db
            table_name = "tiny_model2"

    mem_db.create_tables([_TinyModel2])
    # Directly store a non-JSON string bypassing JSONField serialisation
    mem_db.execute_sql("INSERT INTO tiny_model2 (payload) VALUES ('not json')")
    row = _TinyModel2.get(_TinyModel2.id == 1)

    from sqlalchemy import Column, Integer
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
    from sqlalchemy.orm import DeclarativeBase

    class _Base2(DeclarativeBase):
        pass

    class _TinySA2(_Base2):
        __tablename__ = "tiny_model2"
        id: Any = Column(Integer, primary_key=True)
        payload: Any = Column(PG_JSONB, nullable=True)

    result = _legacy_row_to_dict(_TinyModel2, row, _TinySA2)
    # normalize_legacy_json_value wraps invalid JSON in __legacy_text__
    assert result["payload"] == {"__legacy_text__": "not json"}


# ---------------------------------------------------------------------------
# Test 2: model insert ordering
# ---------------------------------------------------------------------------


def test_sort_models_produces_fk_safe_order() -> None:
    """peewee.sort_models(ALL_MODELS) orders parents before children."""
    _init_in_memory_legacy_db()
    sorted_models = peewee.sort_models(list(ALL_MODELS))
    names = [m.__name__ for m in sorted_models]

    def _idx(name: str) -> int:
        return names.index(name)

    # User must precede all user-owned models
    assert _idx("User") < _idx("Request")
    assert _idx("User") < _idx("ClientSecret")
    assert _idx("User") < _idx("Collection")

    # Request must precede its children
    assert _idx("Request") < _idx("Summary")
    assert _idx("Request") < _idx("CrawlResult")
    assert _idx("Request") < _idx("LLMCall")
    assert _idx("Request") < _idx("TelegramMessage")

    # Summary precedes SummaryEmbedding
    assert _idx("Summary") < _idx("SummaryEmbedding")


# ---------------------------------------------------------------------------
# Test 3: bytes round-trip (Postgres-gated)
# ---------------------------------------------------------------------------


@requires_postgres
def test_bytes_column_round_trip() -> None:
    """SummaryEmbedding.embedding_blob survives the migration unchanged."""
    import asyncio

    from app.cli.migrate_sqlite_to_postgres import run_migration

    # Build a minimal SQLite source with a user + request + summary + embedding
    import tempfile

    from app.cli._legacy_peewee_models._base import database_proxy
    from app.cli._legacy_peewee_models._core import (
        Request as LegRequest,
        Summary as LegSummary,
        SummaryEmbedding as LegEmbedding,
        User as LegUser,
    )

    blob = b"\x01\x02\x03\xff"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        sqlite_path = f.name

    src_db = peewee.SqliteDatabase(sqlite_path)
    database_proxy.initialize(src_db)
    src_db.create_tables([LegUser, LegRequest, LegSummary, LegEmbedding])

    user = LegUser.create(telegram_user_id=1, is_owner=True, server_version=1)
    req = LegRequest.create(
        type="url",
        status="done",
        route_version=1,
        server_version=1,
        is_deleted=False,
    )
    summary = LegSummary.create(
        request=req,
        version=1,
        server_version=1,
        is_read=False,
        is_favorited=False,
        is_deleted=False,
    )
    LegEmbedding.create(
        summary=summary,
        model_name="test",
        model_version="v1",
        embedding_blob=blob,
        dimensions=4,
    )

    exit_code = asyncio.run(
        run_migration(
            source_sqlite=sqlite_path,
            target_postgres=TEST_DATABASE_URL,
            dry_run=False,
            batch_size=500,
            skip_fts_rebuild=True,
        )
    )
    assert exit_code == 0

    # Read back from Postgres
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

    from app.db.models import SummaryEmbedding as SaEmbedding

    async def _fetch() -> bytes | None:
        engine = create_async_engine(TEST_DATABASE_URL)
        async_sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_sm() as session:
                row = await session.scalar(
                    sa.select(SaEmbedding).where(SaEmbedding.summary_id == summary.id)
                )
                return row.embedding_blob if row else None
        finally:
            await engine.dispose()

    result_blob = asyncio.run(_fetch())
    assert result_blob == blob


# ---------------------------------------------------------------------------
# Test 4: dry-run does not write (Postgres-gated)
# ---------------------------------------------------------------------------


@requires_postgres
def test_dry_run_does_not_write() -> None:
    """--dry-run mode counts rows but does not insert into target Postgres."""
    import asyncio
    import tempfile

    from app.cli.migrate_sqlite_to_postgres import run_migration
    from app.cli._legacy_peewee_models._base import database_proxy
    from app.cli._legacy_peewee_models._core import User as LegUser

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        sqlite_path = f.name

    src_db = peewee.SqliteDatabase(sqlite_path)
    database_proxy.initialize(src_db)
    src_db.create_tables([LegUser])
    # Seed one user
    LegUser.create(telegram_user_id=99999999, is_owner=False, server_version=1)

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.db.models import User as SaUser

    async def _count_user() -> int:
        engine = create_async_engine(TEST_DATABASE_URL)
        async_sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_sm() as session:
            cnt = await session.scalar(
                sa.select(sa.func.count()).select_from(SaUser).where(
                    SaUser.telegram_user_id == 99999999
                )
            )
        await engine.dispose()
        return int(cnt or 0)

    before = asyncio.run(_count_user())

    exit_code = asyncio.run(
        run_migration(
            source_sqlite=sqlite_path,
            target_postgres=TEST_DATABASE_URL,
            dry_run=True,
            batch_size=500,
            skip_fts_rebuild=True,
        )
    )
    assert exit_code == 0

    after = asyncio.run(_count_user())
    assert after == before, (
        f"Dry-run inserted rows: before={before}, after={after}"
    )


# ---------------------------------------------------------------------------
# Additional unit tests (no Postgres)
# ---------------------------------------------------------------------------


def test_chunked_splits_correctly() -> None:
    """_chunked yields correct batch sizes."""
    items = list(range(10))
    chunks = list(_chunked(iter(items), 3))
    assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_chunked_empty() -> None:
    assert list(_chunked(iter([]), 5)) == []


def test_resolve_sa_model_known() -> None:
    """_resolve_sa_model returns the correct SA class for known models."""
    _init_in_memory_legacy_db()
    from app.cli._legacy_peewee_models._core import Request as LegRequest
    from app.db.models import Request as SaRequest

    result = _resolve_sa_model(LegRequest)
    assert result is SaRequest


def test_resolve_sa_model_unknown() -> None:
    """_resolve_sa_model returns None for classes not in SA models."""

    class _Phantom(peewee.Model):
        pass

    assert _resolve_sa_model(_Phantom) is None


def test_is_json_column_detects_jsonb() -> None:
    """_is_json_column returns True for JSONB columns."""
    from sqlalchemy import Column, Integer
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    col_json = Column("data", PG_JSONB)
    col_int = Column("id", Integer)

    # Simulate bound column (needs type attribute directly)
    # Use real Column instances via Table binding
    from sqlalchemy import Table, MetaData

    meta = MetaData()
    tbl = Table("t", meta, Column("data", PG_JSONB), Column("id", Integer))
    assert _is_json_column(tbl.c.data) is True
    assert _is_json_column(tbl.c.id) is False


def test_fk_field_column_name_mapping() -> None:
    """FK fields in legacy models expose the _id-suffixed column_name."""
    _init_in_memory_legacy_db()
    from app.cli._legacy_peewee_models._signal import Subscription

    fields = Subscription._meta.fields
    assert fields["user"].column_name == "user_id"
    assert fields["source"].column_name == "source_id"
