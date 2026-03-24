from __future__ import annotations

from datetime import datetime

import pytest

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import CreateGoalRequest
from app.api.services.user_goal_service import UserGoalService
from app.core.time_utils import UTC
from app.db.models import Collection, CollectionItem, Request, Summary, SummaryTag, Tag, User


def _create_summary(*, user_id: int, created_at: datetime | None = None) -> Summary:
    request = Request.create(
        user_id=user_id,
        input_url=f"https://example.com/{user_id}-{Request.select().count()}",
        normalized_url=f"https://example.com/{user_id}-{Request.select().count()}",
        status="completed",
        type="url",
        created_at=created_at or datetime.now(UTC),
    )
    return Summary.create(
        request=request.id,
        lang="en",
        json_payload={"summary_250": "Short", "tldr": "TLDR", "key_ideas": ["idea"]},
        created_at=created_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_user_goal_service_upserts_lists_and_deletes_goals(db) -> None:
    user = User.create(telegram_user_id=7101, username="goal-user")
    service = UserGoalService(db)

    created = await service.upsert_goal(
        user_id=user.telegram_user_id,
        body=CreateGoalRequest(goal_type="daily", target_count=3),
    )
    assert created["goalType"] == "daily"
    assert created["targetCount"] == 3

    updated = await service.upsert_goal(
        user_id=user.telegram_user_id,
        body=CreateGoalRequest(goal_type="daily", target_count=5),
    )
    assert updated["id"] == created["id"]
    assert updated["targetCount"] == 5

    listed = await service.list_goals(user_id=user.telegram_user_id)
    assert len(listed) == 1
    assert listed[0]["targetCount"] == 5

    await service.delete_global_goal(user_id=user.telegram_user_id, goal_type="daily")
    assert await service.list_goals(user_id=user.telegram_user_id) == []


@pytest.mark.asyncio
async def test_user_goal_service_validates_scope_ownership_and_reports_progress(db) -> None:
    user = User.create(telegram_user_id=7102, username="scoped-goal-user")
    other = User.create(telegram_user_id=7103, username="other-user")
    service = UserGoalService(db)

    tag = Tag.create(user=user.telegram_user_id, name="AI", normalized_name="ai")
    collection = Collection.create(user=user.telegram_user_id, name="Reading list")
    summary = _create_summary(user_id=user.telegram_user_id)
    SummaryTag.create(summary=summary.id, tag=tag.id)
    CollectionItem.create(collection=collection.id, summary=summary.id)

    await service.upsert_goal(
        user_id=user.telegram_user_id,
        body=CreateGoalRequest(
            goal_type="daily", target_count=1, scope_type="tag", scope_id=tag.id
        ),
    )
    await service.upsert_goal(
        user_id=user.telegram_user_id,
        body=CreateGoalRequest(
            goal_type="daily",
            target_count=1,
            scope_type="collection",
            scope_id=collection.id,
        ),
    )
    await service.upsert_goal(
        user_id=user.telegram_user_id,
        body=CreateGoalRequest(goal_type="daily", target_count=1),
    )

    progress = await service.get_goal_progress(user_id=user.telegram_user_id)
    assert len(progress) == 3
    assert all(item["currentCount"] >= 1 for item in progress)
    assert all(item["achieved"] is True for item in progress)
    assert {item["scopeName"] for item in progress if item["scopeType"] != "global"} == {
        "AI",
        "Reading list",
    }

    foreign_tag = Tag.create(user=other.telegram_user_id, name="Other", normalized_name="other")
    with pytest.raises(ResourceNotFoundError):
        await service.upsert_goal(
            user_id=user.telegram_user_id,
            body=CreateGoalRequest(
                goal_type="weekly",
                target_count=2,
                scope_type="tag",
                scope_id=foreign_tag.id,
            ),
        )
