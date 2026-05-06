from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.mcp.signal_service import SignalMcpService


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def scalars(self, _query: Any) -> _ScalarResult:
        return _ScalarResult(self._rows)


class _Database:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def session(self) -> _Session:
        return _Session(self._rows)


def _context(rows: list[Any], user_id: int | None = None) -> SimpleNamespace:
    runtime = SimpleNamespace(database=_Database(rows))
    return SimpleNamespace(user_id=user_id, ensure_runtime=lambda: runtime)


@pytest.mark.asyncio
async def test_list_sources_uses_runtime_database_session() -> None:
    source = SimpleNamespace(
        id=1,
        kind="rss",
        external_id="feed-1",
        url="https://example.com/feed.xml",
        title="Example",
        is_active=True,
        fetch_error_count=0,
        last_error=None,
    )

    payload = await SignalMcpService(_context([source])).list_sources()

    assert payload == {
        "sources": [
            {
                "id": 1,
                "kind": "rss",
                "external_id": "feed-1",
                "url": "https://example.com/feed.xml",
                "title": "Example",
                "is_active": True,
                "fetch_error_count": 0,
                "last_error": None,
            }
        ]
    }


@pytest.mark.asyncio
async def test_list_signals_uses_runtime_database_session() -> None:
    source = SimpleNamespace(kind="rss", title="Example")
    feed_item = SimpleNamespace(title="Article", canonical_url="https://example.com", source=source)
    signal = SimpleNamespace(
        id=3,
        status="candidate",
        final_score=0.91,
        filter_stage="heuristic",
        feed_item=feed_item,
        topic_id=7,
        topic=SimpleNamespace(name="AI"),
    )

    payload = await SignalMcpService(_context([signal], user_id=42)).list_signals(
        status="candidate"
    )

    assert payload == {
        "signals": [
            {
                "id": 3,
                "status": "candidate",
                "final_score": 0.91,
                "filter_stage": "heuristic",
                "title": "Article",
                "url": "https://example.com",
                "source_kind": "rss",
                "source_title": "Example",
                "topic_name": "AI",
            }
        ]
    }
