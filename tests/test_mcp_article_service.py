from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.db.models import TopicSearchIndex
from app.mcp.article_service import ArticleReadService
from app.mcp.context import McpServerContext
from app.mcp.helpers import isotime
from tests.mcp_test_utils import insert_scoped_summary

pytest_plugins = ("tests.mcp_test_support",)

if TYPE_CHECKING:
    import pytest

    from app.db.session import DatabaseSessionManager


def test_isotime_formats_utc_cleanly() -> None:
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert isotime(aware) == "2026-01-01T12:00:00Z"
    assert isotime(naive) == "2026-01-01T12:00:00Z"


def test_list_articles_tag_filter_paginates_correctly(mcp_test_db: DatabaseSessionManager) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid_old, _ = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/old-ai",
        title="Old AI",
        tags=["#ai"],
        created_at=now.replace(hour=10),
    )
    insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/middle",
        title="Middle",
        tags=["#other"],
        created_at=now.replace(hour=11),
    )
    sid_new, _ = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/new-ai",
        title="New AI",
        tags=["#ai"],
        created_at=now.replace(hour=12),
    )

    service = ArticleReadService(McpServerContext(user_id=1))
    page1 = service.list_articles(limit=1, offset=0, tag="ai")
    page2 = service.list_articles(limit=1, offset=1, tag="ai")

    assert page1["total"] == 2
    assert page1["articles"][0]["summary_id"] == sid_new
    assert page1["has_more"] is True

    assert page2["total"] == 2
    assert page2["articles"][0]["summary_id"] == sid_old
    assert page2["has_more"] is False


def test_search_articles_preserves_fts_order_and_scope(
    mcp_test_db: DatabaseSessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid_user1_new, req_user1_new = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/user1-new",
        title="User1 New",
        tags=["#topic"],
        created_at=now.replace(hour=12),
    )
    sid_user1_old, req_user1_old = insert_scoped_summary(
        db=mcp_test_db,
        user_id=1,
        url="https://example.com/user1-old",
        title="User1 Old",
        tags=["#topic"],
        created_at=now.replace(hour=10),
    )
    sid_user2, req_user2 = insert_scoped_summary(
        db=mcp_test_db,
        user_id=2,
        url="https://example.com/user2",
        title="User2",
        tags=["#topic"],
        created_at=now.replace(hour=11),
    )

    class FakeFtsResult:
        def __init__(self, rows: list[dict[str, Any]]):
            self._rows = rows

        def select(self, *_args: Any, **_kwargs: Any) -> FakeFtsResult:
            return self

        def limit(self, _value: int) -> FakeFtsResult:
            return self

        def dicts(self) -> list[dict[str, Any]]:
            return self._rows

    fts_rows = [
        {"request_id": req_user2, "rank": 0.1},
        {"request_id": req_user1_old, "rank": 0.2},
        {"request_id": req_user1_new, "rank": 0.3},
    ]
    monkeypatch.setattr(TopicSearchIndex, "search", lambda _query: FakeFtsResult(fts_rows))

    payload = ArticleReadService(McpServerContext(user_id=1)).search_articles("topic", limit=10)
    summary_ids = [row["summary_id"] for row in payload["results"]]

    assert sid_user2 not in summary_ids
    assert summary_ids == [sid_user1_old, sid_user1_new]
