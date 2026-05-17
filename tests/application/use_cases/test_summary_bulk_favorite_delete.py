"""Tests for bulk-favorite and bulk-delete actions.

Mirrors the contract pinned by test_summary_bulk_actions for
mark-read: param threading through use case to repo, dedup,
batch-size cap, and empty-input no-op.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.summary_read_model import SummaryReadModelUseCase


class _Repo:
    def __init__(self, rows: int = 0) -> None:
        self.async_bulk_set_summaries_favorite = AsyncMock(return_value=rows)
        self.async_bulk_soft_delete_summaries = AsyncMock(return_value=rows)


@pytest.mark.asyncio
async def test_bulk_favorite_threads_and_returns_count() -> None:
    repo = _Repo(rows=2)
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )
    out = await use_case.bulk_set_favorite(
        user_id=7, summary_ids=[10, 11], value=True
    )
    assert out == 2
    call = repo.async_bulk_set_summaries_favorite.await_args
    assert call is not None
    assert call.kwargs["user_id"] == 7
    assert call.kwargs["summary_ids"] == [10, 11]
    assert call.kwargs["value"] is True


@pytest.mark.asyncio
async def test_bulk_favorite_empty_input_noop() -> None:
    repo = _Repo()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )
    out = await use_case.bulk_set_favorite(user_id=7, summary_ids=[], value=True)
    assert out == 0
    repo.async_bulk_set_summaries_favorite.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_threads_and_returns_count() -> None:
    repo = _Repo(rows=3)
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )
    out = await use_case.bulk_delete(user_id=7, summary_ids=[10, 11, 12])
    assert out == 3
    call = repo.async_bulk_soft_delete_summaries.await_args
    assert call is not None
    assert call.kwargs["user_id"] == 7
    assert call.kwargs["summary_ids"] == [10, 11, 12]


@pytest.mark.asyncio
async def test_bulk_delete_dedupes_and_caps() -> None:
    repo = _Repo()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )
    await use_case.bulk_delete(user_id=7, summary_ids=[1, 2, 1])
    call = repo.async_bulk_soft_delete_summaries.await_args
    assert call.kwargs["summary_ids"] == [1, 2]

    with pytest.raises(ValueError):
        await use_case.bulk_delete(user_id=7, summary_ids=list(range(1001)))
