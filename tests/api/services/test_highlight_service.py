from __future__ import annotations

import uuid

import pytest

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import CreateHighlightRequest, UpdateHighlightRequest
from app.api.services.highlight_service import SummaryHighlightService
from app.db.models import Request, Summary, SummaryHighlight, User


def _create_summary(*, user_id: int, url_suffix: str = "summary") -> Summary:
    request = Request.create(
        user_id=user_id,
        input_url=f"https://example.com/{url_suffix}",
        normalized_url=f"https://example.com/{url_suffix}",
        status="completed",
        type="url",
    )
    return Summary.create(
        request=request.id,
        lang="en",
        json_payload={"summary_250": "Short", "tldr": "TLDR", "key_ideas": ["idea"]},
    )


@pytest.mark.asyncio
async def test_highlight_service_crud_round_trip(db) -> None:
    user = User.create(telegram_user_id=7001, username="highlight-user")
    summary = _create_summary(user_id=user.telegram_user_id)
    service = SummaryHighlightService(db)

    created = await service.create_highlight(
        user_id=user.telegram_user_id,
        summary_id=summary.id,
        body=CreateHighlightRequest(text="Important text", color="yellow"),
    )

    listed = await service.list_highlights(user_id=user.telegram_user_id, summary_id=summary.id)
    assert len(listed) == 1
    assert listed[0]["text"] == "Important text"
    assert created["id"] == listed[0]["id"]

    updated = await service.update_highlight(
        user_id=user.telegram_user_id,
        summary_id=summary.id,
        highlight_id=created["id"],
        body=UpdateHighlightRequest(color="blue", note="revisit"),
    )
    assert updated["color"] == "blue"
    assert updated["note"] == "revisit"

    await service.delete_highlight(
        user_id=user.telegram_user_id,
        summary_id=summary.id,
        highlight_id=created["id"],
    )
    assert await service.list_highlights(user_id=user.telegram_user_id, summary_id=summary.id) == []


@pytest.mark.asyncio
async def test_highlight_service_rejects_unowned_summary_and_missing_highlight(db) -> None:
    owner = User.create(telegram_user_id=7002, username="owner")
    other = User.create(telegram_user_id=7003, username="other")
    summary = _create_summary(user_id=owner.telegram_user_id, url_suffix="owner-summary")
    service = SummaryHighlightService(db)

    with pytest.raises(ResourceNotFoundError):
        await service.list_highlights(user_id=other.telegram_user_id, summary_id=summary.id)

    SummaryHighlight.create(
        id=uuid.uuid4(),
        user=owner.telegram_user_id,
        summary=summary.id,
        text="Owned highlight",
    )

    with pytest.raises(ResourceNotFoundError):
        await service.update_highlight(
            user_id=owner.telegram_user_id,
            summary_id=summary.id,
            highlight_id=str(uuid.uuid4()),
            body=UpdateHighlightRequest(note="missing"),
        )
