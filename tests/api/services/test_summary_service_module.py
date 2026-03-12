from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.exceptions import ResourceNotFoundError
from app.api.services.summary_service import SummaryService


@pytest.mark.asyncio
async def test_get_user_summaries_delegates_to_use_case() -> None:
    use_case = MagicMock()
    use_case.get_user_summaries = AsyncMock(return_value=([{"id": 1}], 1, 0))

    with patch.object(SummaryService, "_build_use_case", return_value=use_case):
        result = await SummaryService.get_user_summaries(user_id=1, limit=5, offset=2, lang="en")

    assert result == ([{"id": 1}], 1, 0)
    use_case.get_user_summaries.assert_awaited_once_with(
        user_id=1,
        limit=5,
        offset=2,
        is_read=None,
        is_favorited=None,
        lang="en",
        start_date=None,
        end_date=None,
        sort="created_at_desc",
    )


@pytest.mark.asyncio
async def test_get_summary_by_id_raises_when_not_found() -> None:
    use_case = MagicMock()
    use_case.get_summary_by_id_for_user = AsyncMock(return_value=None)

    with patch.object(SummaryService, "_build_use_case", return_value=use_case):
        with pytest.raises(ResourceNotFoundError):
            await SummaryService.get_summary_by_id(user_id=1, summary_id=2)


@pytest.mark.asyncio
async def test_update_delete_and_toggle_favorite_delegate_and_enforce_not_found() -> None:
    use_case = MagicMock()
    use_case.update_summary = AsyncMock(return_value={"id": 2, "is_read": True})
    use_case.soft_delete_summary = AsyncMock(return_value=True)
    use_case.toggle_favorite = AsyncMock(return_value=True)

    with patch.object(SummaryService, "_build_use_case", return_value=use_case):
        updated = await SummaryService.update_summary(user_id=1, summary_id=2, is_read=True)
        assert updated["is_read"] is True

        await SummaryService.delete_summary(user_id=1, summary_id=2)
        favorited = await SummaryService.toggle_favorite(user_id=1, summary_id=2)
        assert favorited is True

    missing_use_case = MagicMock()
    missing_use_case.update_summary = AsyncMock(return_value=None)
    missing_use_case.soft_delete_summary = AsyncMock(return_value=False)
    missing_use_case.toggle_favorite = AsyncMock(return_value=None)

    with patch.object(SummaryService, "_build_use_case", return_value=missing_use_case):
        with pytest.raises(ResourceNotFoundError):
            await SummaryService.update_summary(user_id=1, summary_id=2, is_read=False)
        with pytest.raises(ResourceNotFoundError):
            await SummaryService.delete_summary(user_id=1, summary_id=2)
        with pytest.raises(ResourceNotFoundError):
            await SummaryService.toggle_favorite(user_id=1, summary_id=2)
