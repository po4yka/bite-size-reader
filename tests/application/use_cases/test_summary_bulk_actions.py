"""Tests for bulk action use-case methods on summaries.

Per [[overhaul-articles-management]]: ArticlesPage needs multi-select
bulk actions (mark-read, mark-unread, favorite, delete). This test
covers the use-case-layer threading for the most-requested action.
Repo-layer SQL coverage belongs in the infrastructure tests.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.summary_read_model import SummaryReadModelUseCase


class _SummaryRepoBulkSpy:
    def __init__(self, *, rows_affected: int = 0) -> None:
        self.async_bulk_mark_summaries_as_read = AsyncMock(
            return_value=rows_affected
        )


@pytest.mark.asyncio
async def test_bulk_mark_as_read_threads_user_and_ids() -> None:
    repo = _SummaryRepoBulkSpy(rows_affected=3)
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    rows = await use_case.bulk_mark_as_read(user_id=42, summary_ids=[1, 2, 3])

    assert rows == 3
    call = repo.async_bulk_mark_summaries_as_read.await_args
    assert call is not None
    assert call.kwargs["user_id"] == 42
    assert call.kwargs["summary_ids"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_bulk_mark_as_read_empty_ids_is_noop() -> None:
    repo = _SummaryRepoBulkSpy()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    rows = await use_case.bulk_mark_as_read(user_id=42, summary_ids=[])

    assert rows == 0
    # The repository must not be called for an empty list — avoids
    # an UPDATE with WHERE id IN () which is a no-op but wasteful.
    repo.async_bulk_mark_summaries_as_read.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_mark_as_read_dedupes_input() -> None:
    repo = _SummaryRepoBulkSpy(rows_affected=2)
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    await use_case.bulk_mark_as_read(user_id=42, summary_ids=[1, 2, 1, 2, 1])

    call = repo.async_bulk_mark_summaries_as_read.await_args
    assert call is not None
    # Deduped + order-preserving.
    assert call.kwargs["summary_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_bulk_mark_as_read_rejects_excessively_large_batch() -> None:
    repo = _SummaryRepoBulkSpy()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )
    huge = list(range(1, 1001))  # 1000 ids — over the cap

    with pytest.raises(ValueError):
        await use_case.bulk_mark_as_read(user_id=42, summary_ids=huge)
