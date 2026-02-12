from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

import pytest

import app.mcp.server as mcp_server
from app.db.database import Database
from app.db.models import Summary, TopicSearchIndex, database_proxy


@pytest.fixture
def mcp_test_db(tmp_path):
    """Create isolated DB and bind it to Peewee proxy for MCP tests."""
    old_proxy_obj = database_proxy.obj
    db_path = tmp_path / "mcp.db"
    database = Database(str(db_path))
    database.migrate()
    database_proxy.initialize(database._database)
    yield database
    database._database.close()
    database_proxy.initialize(old_proxy_obj)


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Reset global MCP server state between tests."""
    mcp_server._set_user_scope(None)
    mcp_server._chroma_service = None
    mcp_server._chroma_last_failed_at = None
    mcp_server._local_vector_service = None
    mcp_server._local_vector_last_failed_at = None
    yield
    mcp_server._set_user_scope(None)
    mcp_server._chroma_service = None
    mcp_server._chroma_last_failed_at = None
    mcp_server._local_vector_service = None
    mcp_server._local_vector_last_failed_at = None


def _insert_summary(
    *,
    db: Database,
    user_id: int,
    url: str,
    title: str,
    tags: list[str],
    created_at: datetime,
) -> tuple[int, int]:
    request_id = db.create_request(
        type_="url",
        status="completed",
        correlation_id=f"cid-{user_id}-{url}",
        chat_id=1,
        user_id=user_id,
        input_url=url,
        normalized_url=url,
    )
    summary_id = db.insert_summary(
        request_id=request_id,
        lang="en",
        json_payload={
            "summary_250": f"Summary for {title}",
            "tldr": f"TLDR {title}",
            "topic_tags": tags,
            "metadata": {"title": title, "domain": "example.com"},
        },
    )
    Summary.update(
        {
            Summary.created_at: created_at,
            Summary.updated_at: created_at,
        }
    ).where(Summary.id == summary_id).execute()
    return summary_id, request_id


def test_isotime_formats_utc_cleanly() -> None:
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert mcp_server._isotime(aware) == "2026-01-01T12:00:00Z"
    assert mcp_server._isotime(naive) == "2026-01-01T12:00:00Z"


def test_list_articles_tag_filter_paginates_correctly(mcp_test_db: Database) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid_old, _ = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/old-ai",
        title="Old AI",
        tags=["#ai"],
        created_at=now.replace(hour=10),
    )
    _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/middle",
        title="Middle",
        tags=["#other"],
        created_at=now.replace(hour=11),
    )
    sid_new, _ = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/new-ai",
        title="New AI",
        tags=["#ai"],
        created_at=now.replace(hour=12),
    )

    mcp_server._set_user_scope(1)

    page1 = json.loads(mcp_server.list_articles(limit=1, offset=0, tag="ai"))
    page2 = json.loads(mcp_server.list_articles(limit=1, offset=1, tag="ai"))

    assert page1["total"] == 2
    assert page1["articles"][0]["summary_id"] == sid_new
    assert page1["has_more"] is True

    assert page2["total"] == 2
    assert page2["articles"][0]["summary_id"] == sid_old
    assert page2["has_more"] is False


def test_search_articles_preserves_fts_order_and_scope(
    mcp_test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid_user1_new, req_user1_new = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/user1-new",
        title="User1 New",
        tags=["#topic"],
        created_at=now.replace(hour=12),
    )
    sid_user1_old, req_user1_old = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/user1-old",
        title="User1 Old",
        tags=["#topic"],
        created_at=now.replace(hour=10),
    )
    sid_user2, req_user2 = _insert_summary(
        db=mcp_test_db,
        user_id=2,
        url="https://example.com/user2",
        title="User2",
        tags=["#topic"],
        created_at=now.replace(hour=11),
    )

    class _FakeFtsResult:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def select(self, *_args: Any, **_kwargs: Any) -> _FakeFtsResult:
            return self

        def limit(self, _value: int) -> _FakeFtsResult:
            return self

        def dicts(self) -> list[dict[str, Any]]:
            return self._rows

    fts_rows = [
        {"request_id": req_user2, "rank": 0.1},
        {"request_id": req_user1_old, "rank": 0.2},
        {"request_id": req_user1_new, "rank": 0.3},
    ]
    monkeypatch.setattr(TopicSearchIndex, "search", lambda _query: _FakeFtsResult(fts_rows))

    mcp_server._set_user_scope(1)
    payload = json.loads(mcp_server.search_articles("topic", limit=10))
    summary_ids = [row["summary_id"] for row in payload["results"]]

    assert sid_user2 not in summary_ids
    assert summary_ids == [sid_user1_old, sid_user1_new]


def test_run_server_rejects_insecure_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_init_database", lambda _db_path=None: None)
    monkeypatch.setattr(mcp_server.mcp, "run", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="non-loopback"):
        mcp_server.run_server(transport="sse", host="0.0.0.0", user_id=1)

    with pytest.raises(ValueError, match="unscoped"):
        mcp_server.run_server(transport="sse", host="127.0.0.1", user_id=None)


@pytest.mark.asyncio
async def test_get_chroma_service_retries_after_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.config as app_config

    clock = {"now": 0.0}
    attempts = {"count": 0}

    def _fake_monotonic() -> float:
        return clock["now"]

    def _failing_load_config(*_args: Any, **_kwargs: Any):
        attempts["count"] += 1
        raise RuntimeError("chroma down")

    monkeypatch.setattr(mcp_server.time, "monotonic", _fake_monotonic)
    monkeypatch.setattr(app_config, "load_config", _failing_load_config)
    monkeypatch.setattr(mcp_server, "_CHROMA_RETRY_INTERVAL_SEC", 60.0)

    assert await mcp_server._get_chroma_service() is None
    assert attempts["count"] == 1

    clock["now"] = 10.0
    assert await mcp_server._get_chroma_service() is None
    assert attempts["count"] == 1

    clock["now"] = 61.0
    assert await mcp_server._get_chroma_service() is None
    assert attempts["count"] == 2


def test_cli_uses_mcp_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.cli.mcp_server as mcp_cli
    import app.mcp.server as server_module

    captured: dict[str, Any] = {}

    def _fake_run_server(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("MCP_TRANSPORT", "sse")
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "9333")
    monkeypatch.setenv("MCP_USER_ID", "4242")
    monkeypatch.setattr(server_module, "run_server", _fake_run_server)
    monkeypatch.setattr(sys, "argv", ["bsr-mcp-server"])

    mcp_cli.main()

    assert captured["transport"] == "sse"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9333
    assert captured["user_id"] == 4242


class _FakeChromaResult:
    def __init__(
        self,
        *,
        request_id: int,
        summary_id: int,
        similarity_score: float,
        snippet: str,
        chunk_id: str | None = None,
        window_id: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.summary_id = summary_id
        self.similarity_score = similarity_score
        self.url = f"https://example.com/{summary_id}"
        self.title = f"title-{summary_id}"
        self.snippet = snippet
        self.text = snippet
        self.source = "example.com"
        self.published_at = None
        self.window_id = window_id
        self.window_index = None
        self.chunk_id = chunk_id
        self.section = "body"
        self.topics = ["#topic"]
        self.local_keywords = ["keyword"]
        self.semantic_boosters: list[str] = []
        self.local_summary = snippet


class _FakeChromaSearchPayload:
    def __init__(self, results: list[_FakeChromaResult], has_more: bool = False) -> None:
        self.results = results
        self.has_more = has_more


class _FakeChromaService:
    def __init__(self, results: list[_FakeChromaResult]) -> None:
        self._results = results

    async def search(self, *_args: Any, **_kwargs: Any) -> _FakeChromaSearchPayload:
        return _FakeChromaSearchPayload(self._results, has_more=False)


@pytest.mark.asyncio
async def test_semantic_search_groups_chunks_and_min_similarity(
    mcp_test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, req1 = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/one",
        title="One",
        tags=["#ai"],
        created_at=now,
    )
    sid2, req2 = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/two",
        title="Two",
        tags=["#ai"],
        created_at=now.replace(hour=11),
    )
    mcp_server._set_user_scope(1)

    fake_results = [
        _FakeChromaResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.91,
            snippet="chunk-1",
            chunk_id="chunk-a",
            window_id="w-a",
        ),
        _FakeChromaResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.83,
            snippet="chunk-2",
            chunk_id="chunk-b",
            window_id="w-b",
        ),
        _FakeChromaResult(
            request_id=req2,
            summary_id=sid2,
            similarity_score=0.61,
            snippet="low-sim",
            chunk_id="chunk-c",
            window_id="w-c",
        ),
    ]

    async def _fake_chroma() -> _FakeChromaService:
        return _FakeChromaService(fake_results)

    monkeypatch.setattr(mcp_server, "_get_chroma_service", _fake_chroma)

    payload = json.loads(
        await mcp_server.semantic_search(
            "ai policy",
            limit=10,
            min_similarity=0.7,
            include_chunks=True,
        )
    )
    results = payload["results"]

    assert payload["search_backend"] == "chroma"
    assert len(results) == 1
    assert results[0]["summary_id"] == sid1
    assert results[0]["similarity_score"] == pytest.approx(0.91)
    assert results[0]["semantic_match_count"] == 2
    assert len(results[0]["semantic_matches"]) == 2


@pytest.mark.asyncio
async def test_semantic_search_keyword_fallback_when_semantic_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_chroma() -> None:
        return None

    async def _no_local(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(mcp_server, "_get_chroma_service", _no_chroma)
    monkeypatch.setattr(mcp_server, "_search_local_vectors", _no_local)
    monkeypatch.setattr(
        mcp_server,
        "search_articles",
        lambda query, limit=10: json.dumps(
            {
                "results": [{"summary_id": 101, "title": "keyword result"}],
                "total": 1,
                "query": query,
            }
        ),
    )

    payload = json.loads(await mcp_server.semantic_search("topic", limit=5))
    assert payload["search_type"] == "keyword_fallback"
    assert payload["search_backend"] == "fts"
    assert payload["results"][0]["summary_id"] == 101


@pytest.mark.asyncio
async def test_find_similar_articles_excludes_source_summary(
    mcp_test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, req1 = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/seed",
        title="Seed",
        tags=["#ai"],
        created_at=now,
    )
    sid2, req2 = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/other",
        title="Other",
        tags=["#ai"],
        created_at=now.replace(hour=11),
    )
    mcp_server._set_user_scope(1)

    fake_results = [
        _FakeChromaResult(
            request_id=req1,
            summary_id=sid1,
            similarity_score=0.95,
            snippet="seed match",
            chunk_id="chunk-seed",
            window_id="w-seed",
        ),
        _FakeChromaResult(
            request_id=req2,
            summary_id=sid2,
            similarity_score=0.88,
            snippet="other match",
            chunk_id="chunk-other",
            window_id="w-other",
        ),
    ]

    async def _fake_chroma() -> _FakeChromaService:
        return _FakeChromaService(fake_results)

    monkeypatch.setattr(mcp_server, "_get_chroma_service", _fake_chroma)

    payload = json.loads(await mcp_server.find_similar_articles(summary_id=sid1, limit=10))
    result_ids = [row["summary_id"] for row in payload["results"]]

    assert sid1 not in result_ids
    assert sid2 in result_ids


@pytest.mark.asyncio
async def test_chroma_sync_gap_reports_missing_and_extra(
    mcp_test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid1, _ = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/sync-a",
        title="Sync A",
        tags=["#sync"],
        created_at=now,
    )
    sid2, _ = _insert_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/sync-b",
        title="Sync B",
        tags=["#sync"],
        created_at=now.replace(hour=11),
    )
    mcp_server._set_user_scope(1)

    class _FakeStore:
        def get_indexed_summary_ids(
            self, *, user_id: int | None = None, limit: int | None = 5000
        ) -> set[int]:
            _ = (user_id, limit)
            return {sid2, 99999}

    class _FakeChroma:
        _vector_store = _FakeStore()

    async def _fake_chroma() -> _FakeChroma:
        return _FakeChroma()

    monkeypatch.setattr(mcp_server, "_get_chroma_service", _fake_chroma)

    payload = json.loads(await mcp_server.chroma_sync_gap(max_scan=1000, sample_size=10))
    assert payload["missing_in_chroma_count"] == 1
    assert sid1 in payload["missing_in_chroma_sample"]
    assert payload["missing_in_sqlite_count"] == 1
    assert 99999 in payload["missing_in_sqlite_sample"]
