"""
Tests for favorites (direct calls).
"""

import pytest

from app.api.routers import summaries
from app.db.models import Request, Summary


@pytest.mark.asyncio
async def test_toggle_favorite(db, user_factory):
    user = user_factory(username="fav_user")
    user_context = {"user_id": user.telegram_user_id}

    # Manually create summary
    req = Request.create(
        user_id=user.telegram_user_id, input_url="http://test1.com", status="completed", type="url"
    )

    summary = Summary.create(
        request=req.id,
        lang="en",
        is_read=False,
        version=1,
        json_payload={},
        # is_favorited default False
    )

    assert not summary.is_favorited

    # Toggle ON
    response = await summaries.toggle_favorite(summary_id=summary.id, user=user_context)
    assert response["success"] is True
    assert response["data"]["is_favorited"] is True

    summary = Summary.get_by_id(summary.id)
    assert summary.is_favorited is True

    # Toggle OFF
    response = await summaries.toggle_favorite(summary_id=summary.id, user=user_context)
    assert response["data"]["is_favorited"] is False

    summary = Summary.get_by_id(summary.id)
    assert summary.is_favorited is False


@pytest.mark.asyncio
async def test_get_summaries_filter(db, user_factory, summary_factory):
    user = user_factory(username="fav_user_filter")
    user_context = {"user_id": user.telegram_user_id}

    # S1: Favorited
    s1 = summary_factory(user=user)
    s1.is_favorited = True
    s1.save()

    # S2: Not Favorited
    s2 = summary_factory(user=user)

    # All
    resp = await summaries.get_summaries(
        user=user_context,
        limit=20,
        offset=0,
        sort="created_at_desc",
        is_read=None,
        is_favorited=None,
        lang=None,
        start_date=None,
        end_date=None,
    )
    data = resp["data"]["summaries"]
    ids = [s["id"] for s in data]
    assert s1.id in ids
    assert s2.id in ids

    # Favorites only
    resp = await summaries.get_summaries(
        user=user_context,
        limit=20,
        offset=0,
        sort="created_at_desc",
        is_read=None,
        is_favorited=True,
        lang=None,
        start_date=None,
        end_date=None,
    )
    data = resp["data"]["summaries"]
    assert len(data) == 1
    assert data[0]["id"] == s1.id

    # Non-favorites
    resp = await summaries.get_summaries(
        user=user_context,
        limit=20,
        offset=0,
        sort="created_at_desc",
        is_read=None,
        is_favorited=False,
        lang=None,
        start_date=None,
        end_date=None,
    )
    data = resp["data"]["summaries"]
    ids = [s["id"] for s in data]
    assert s1.id not in ids
    assert s2.id in ids
