"""Unit tests for the process_import_job Taskiq task.

Tests call _run_import_body directly (no broker, no DB) following the
same pattern as tests for _sync_body in github_sync task tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.import_tasks import _dict_to_bookmark, _run_import_body


# ---------------------------------------------------------------------------
# _dict_to_bookmark
# ---------------------------------------------------------------------------


def test_dict_to_bookmark_minimal():
    bm = _dict_to_bookmark({"url": "https://example.com"})
    assert bm.url == "https://example.com"
    assert bm.title is None
    assert bm.tags == []
    assert bm.created_at is None


def test_dict_to_bookmark_with_timestamp():
    bm = _dict_to_bookmark({"url": "https://x.com", "created_at": "2024-01-15T12:00:00"})
    assert bm.created_at is not None
    assert bm.created_at.year == 2024


def test_dict_to_bookmark_full():
    bm = _dict_to_bookmark({
        "url": "https://example.com",
        "title": "My Title",
        "tags": ["a", "b"],
        "notes": "note",
        "collection_name": "Reading",
        "highlights": [{"text": "hi"}],
        "extra": {"source": "pocket"},
    })
    assert bm.title == "My Title"
    assert bm.tags == ["a", "b"]
    assert bm.notes == "note"
    assert bm.collection_name == "Reading"
    assert bm.highlights == [{"text": "hi"}]
    assert bm.extra == {"source": "pocket"}


# ---------------------------------------------------------------------------
# _run_import_body — missing job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_import_body_missing_job_is_no_op():
    """job_id not found → log and return without touching status."""
    mock_repo = AsyncMock()
    mock_repo.async_get_job.return_value = None

    with patch("app.tasks.import_tasks.ImportJobRepositoryAdapter", return_value=mock_repo):
        await _run_import_body(
            job_id=999,
            user_id=1,
            bookmarks_json=[],
            options={},
            db=MagicMock(),
        )

    mock_repo.async_set_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_import_body — idempotency / non-pending status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["processing", "completed", "failed"])
async def test_run_import_body_skips_non_pending(status: str):
    """Jobs not in 'pending' state are silently skipped (idempotency)."""
    mock_repo = AsyncMock()
    mock_repo.async_get_job.return_value = {"status": status}

    with patch("app.tasks.import_tasks.ImportJobRepositoryAdapter", return_value=mock_repo):
        await _run_import_body(
            job_id=1,
            user_id=1,
            bookmarks_json=[],
            options={},
            db=MagicMock(),
        )

    mock_repo.async_set_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_import_body — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_import_body_runs_use_case_for_pending_job():
    """Pending job: use case is executed with correct command arguments."""
    mock_repo = AsyncMock()
    mock_repo.async_get_job.return_value = {"status": "pending"}

    mock_use_case = AsyncMock()
    mock_use_case_cls = MagicMock(return_value=mock_use_case)

    with (
        patch("app.tasks.import_tasks.ImportJobRepositoryAdapter", return_value=mock_repo),
        patch("app.tasks.import_tasks.BookmarkImportAdapter"),
        patch("app.tasks.import_tasks.ImportBookmarksUseCase", mock_use_case_cls),
    ):
        await _run_import_body(
            job_id=42,
            user_id=7,
            bookmarks_json=[
                {"url": "https://example.com", "tags": [], "extra": {}},
                {"url": "https://other.com", "title": "Other", "tags": ["x"], "extra": {}},
            ],
            options={"dedupe": True},
            db=MagicMock(),
        )

    mock_use_case.execute.assert_awaited_once()
    cmd = mock_use_case.execute.call_args.args[0]
    assert cmd.job_id == 42
    assert cmd.user_id == 7
    assert len(cmd.bookmarks) == 2
    assert cmd.bookmarks[0].url == "https://example.com"
    assert cmd.bookmarks[1].url == "https://other.com"
    assert cmd.options == {"dedupe": True}


# ---------------------------------------------------------------------------
# _run_import_body — duplicate retry safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_import_body_duplicate_retry_safe():
    """Second invocation for an already-processed job is a no-op."""
    mock_use_case = AsyncMock()
    mock_use_case_cls = MagicMock(return_value=mock_use_case)

    call_count = 0

    async def _get_job(job_id: int):
        nonlocal call_count
        call_count += 1
        return {"status": "pending"} if call_count == 1 else {"status": "completed"}

    mock_repo = AsyncMock()
    mock_repo.async_get_job.side_effect = _get_job

    kwargs = {"job_id": 5, "user_id": 1, "bookmarks_json": [], "options": {}, "db": MagicMock()}

    with (
        patch("app.tasks.import_tasks.ImportJobRepositoryAdapter", return_value=mock_repo),
        patch("app.tasks.import_tasks.BookmarkImportAdapter"),
        patch("app.tasks.import_tasks.ImportBookmarksUseCase", mock_use_case_cls),
    ):
        await _run_import_body(**kwargs)
        await _run_import_body(**kwargs)

    assert mock_use_case.execute.await_count == 1
