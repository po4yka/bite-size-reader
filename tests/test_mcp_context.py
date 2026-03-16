from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.db.models import database_proxy
from app.db.session import DatabaseSessionManager
from app.mcp.context import McpServerContext


def test_init_runtime_opens_sqlite_read_only(tmp_path: Any) -> None:
    import peewee

    old_proxy_obj = database_proxy.obj
    db_path = tmp_path / "mcp-read-only.db"

    seed_db = peewee.SqliteDatabase(str(db_path))
    seed_db.connect()
    seed_db.execute_sql("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
    seed_db.execute_sql("INSERT INTO sample(value) VALUES ('seed')")
    seed_db.close()

    db_path.chmod(0o444)
    try:
        context = McpServerContext(db_path=str(db_path))
        context.init_runtime()
        assert database_proxy.obj.execute_sql("SELECT value FROM sample").fetchone() == ("seed",)
        with pytest.raises(peewee.OperationalError):
            database_proxy.obj.execute_sql("INSERT INTO sample(value) VALUES ('write')")
    finally:
        try:
            database_proxy.obj.close()
        except Exception:
            pass
        database_proxy.initialize(old_proxy_obj)
        db_path.chmod(0o644)


@pytest.mark.asyncio
async def test_get_chroma_service_retries_after_backoff(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.di.mcp as mcp_di

    clock = {"now": 0.0}
    attempts = {"count": 0}

    def fake_monotonic() -> float:
        return clock["now"]

    def failing_load_config(*_args: Any, **_kwargs: Any):
        attempts["count"] += 1
        raise RuntimeError("chroma down")

    monkeypatch.setattr(mcp_di.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(mcp_di, "load_config", failing_load_config)

    db_path = tmp_path / "mcp-backoff.db"
    database = DatabaseSessionManager(str(db_path))
    database.migrate()
    database._database.close()

    context = McpServerContext(db_path=str(db_path), chroma_retry_interval_sec=60.0)

    assert await context.get_chroma_service() is None
    assert attempts["count"] == 1

    clock["now"] = 10.0
    assert await context.get_chroma_service() is None
    assert attempts["count"] == 1

    clock["now"] = 61.0
    assert await context.get_chroma_service() is None
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_get_chroma_service_forwards_required_and_timeout(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.di.mcp as mcp_di
    import app.infrastructure.vector.chroma_store as chroma_store_module
    import app.services.chroma_vector_search_service as chroma_service_module
    import app.services.embedding_factory as embedding_factory_module

    captured: dict[str, Any] = {}

    class FakeStore:
        def __init__(self, **kwargs: Any) -> None:
            captured["store_kwargs"] = kwargs

    class FakeService:
        def __init__(self, **kwargs: Any) -> None:
            self._vector_store = kwargs["vector_store"]

    monkeypatch.setattr(
        mcp_di,
        "load_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            vector_store=SimpleNamespace(
                host="http://localhost:8000",
                auth_token="token",
                environment="test",
                user_scope="scope",
                collection_version="v5",
                required=True,
                connection_timeout=7.5,
            ),
            embedding=object(),
        ),
    )
    monkeypatch.setattr(embedding_factory_module, "create_embedding_service", lambda _cfg: object())
    monkeypatch.setattr(chroma_store_module, "ChromaVectorStore", FakeStore)
    monkeypatch.setattr(chroma_service_module, "ChromaVectorSearchService", FakeService)

    db_path = tmp_path / "mcp-context.db"
    database = DatabaseSessionManager(str(db_path))
    database.migrate()
    database._database.close()

    context = McpServerContext(db_path=str(db_path))
    await context.get_chroma_service()

    assert captured["store_kwargs"] == {
        "host": "http://localhost:8000",
        "auth_token": "token",
        "environment": "test",
        "user_scope": "scope",
        "collection_version": "v5",
        "required": True,
        "connection_timeout": 7.5,
    }
