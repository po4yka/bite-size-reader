from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.db.models import UserInteraction
from tests.db_helpers_async import update_user_interaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _insert_interaction(session: AsyncSession) -> int:
    row = UserInteraction(
        user_id=1,
        interaction_type="message",
        response_sent=False,
        response_type="initial",
        error_occurred=True,
        error_message="pending",
        processing_time_ms=250,
        request_id=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


async def test_update_user_interaction_updates_allowed_fields(session: AsyncSession) -> None:
    interaction_id = await _insert_interaction(session)

    await update_user_interaction(
        session,
        interaction_id,
        updates={
            "response_sent": True,
            "response_type": "summary",
            "error_occurred": False,
            "error_message": None,
            "processing_time_ms": 1234,
            "request_id": None,
        },
    )

    row = await session.scalar(select(UserInteraction).where(UserInteraction.id == interaction_id))
    assert row is not None
    assert row.response_sent is True
    assert row.response_type == "summary"
    assert row.error_occurred is False
    assert row.error_message is None
    assert row.processing_time_ms == 1234


async def test_update_user_interaction_rejects_unknown_field(session: AsyncSession) -> None:
    interaction_id = await _insert_interaction(session)

    with pytest.raises(ValueError):
        await update_user_interaction(session, interaction_id, updates={"invalid": "noop"})


async def test_update_user_interaction_ignores_empty_updates(session: AsyncSession) -> None:
    interaction_id = await _insert_interaction(session)
    before = await session.scalar(
        select(UserInteraction).where(UserInteraction.id == interaction_id)
    )
    assert before is not None
    before_state = (
        before.response_sent,
        before.response_type,
        before.error_occurred,
        before.error_message,
        before.processing_time_ms,
        before.request_id,
    )

    await update_user_interaction(session, interaction_id, updates={})

    session.expire_all()
    after = await session.scalar(
        select(UserInteraction).where(UserInteraction.id == interaction_id)
    )
    assert after is not None
    assert (
        after.response_sent,
        after.response_type,
        after.error_occurred,
        after.error_message,
        after.processing_time_ms,
        after.request_id,
    ) == before_state


async def test_update_user_interaction_accepts_legacy_kwargs(session: AsyncSession) -> None:
    interaction_id = await _insert_interaction(session)

    await update_user_interaction(
        session,
        interaction_id,
        response_sent=True,
        response_type="completed",
        error_occurred=False,
        error_message="done",
        processing_time_ms=512,
        request_id=None,
    )

    row = await session.scalar(select(UserInteraction).where(UserInteraction.id == interaction_id))
    assert row is not None
    assert row.response_sent is True
    assert row.response_type == "completed"
    assert row.error_occurred is False
    assert row.error_message == "done"
    assert row.processing_time_ms == 512


async def test_update_user_interaction_rejects_mixed_inputs(session: AsyncSession) -> None:
    interaction_id = await _insert_interaction(session)

    with pytest.raises(ValueError):
        await update_user_interaction(
            session,
            interaction_id,
            updates={"response_sent": True},
            response_type="summary",
        )
