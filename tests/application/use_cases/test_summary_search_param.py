"""Tests for the `search` parameter on the user-summaries list endpoint.

Migrated from [[overhaul-articles-management]] backend slice:
`ArticlesPage.tsx`'s `searchTerm` state currently never reaches the
API. This test pins the API-level contract: callers can pass
`search="kotlin"` and the use case must thread the value through to
the repository, which must apply an ILIKE filter on
`requests.title`. Repo-layer SQL is covered separately in the
infrastructure tests; this test covers the seam between the router,
use case, and port.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.summary_read_model import SummaryReadModelUseCase


class _SummaryRepoSpy:
    def __init__(self) -> None:
        self.async_get_user_summaries = AsyncMock(return_value=([], 0, 0))


@pytest.mark.asyncio
async def test_search_param_is_threaded_to_repository() -> None:
    repo = _SummaryRepoSpy()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    await use_case.get_user_summaries(user_id=42, limit=10, offset=0, search="kotlin")

    call = repo.async_get_user_summaries.await_args
    assert call is not None
    assert call.kwargs.get("search") == "kotlin"


@pytest.mark.asyncio
async def test_search_param_optional_omitted_passes_none() -> None:
    repo = _SummaryRepoSpy()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    await use_case.get_user_summaries(user_id=42, limit=10, offset=0)

    call = repo.async_get_user_summaries.await_args
    assert call is not None
    assert call.kwargs.get("search") is None


@pytest.mark.asyncio
async def test_search_empty_string_normalised_to_none() -> None:
    # An empty search should not pollute the SQL query with a wildcard.
    repo = _SummaryRepoSpy()
    use_case = SummaryReadModelUseCase(
        summary_repository=cast("Any", repo),
        request_repository=AsyncMock(),
        crawl_result_repository=AsyncMock(),
        llm_repository=AsyncMock(),
    )

    await use_case.get_user_summaries(user_id=42, limit=10, offset=0, search="   ")

    call = repo.async_get_user_summaries.await_args
    assert call is not None
    assert call.kwargs.get("search") is None
