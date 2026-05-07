"""Coverage for MessageInteractionRecorder + safe_update_user_interaction."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

from sqlalchemy import select

from app.adapters.telegram.routing.interactions import MessageInteractionRecorder
from app.adapters.telegram.routing.models import PreparedRouteContext
from app.db.models import UserInteraction
from app.db.user_interactions import (
    async_safe_update_user_interaction,
    safe_update_user_interaction,
)
from app.domain.models.request import RequestStatus
from app.infrastructure.persistence.repositories.request_repository import (
    RequestRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.user_repository import (
    UserRepositoryAdapter,
)
from tests.conftest import make_test_app_config

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


def _make_config():
    return make_test_app_config()


async def test_message_router_logs_interaction(
    database: Database, session: AsyncSession
) -> None:
    cfg = _make_config()
    recorder = MessageInteractionRecorder(
        user_repo=UserRepositoryAdapter(database),
        structured_output_enabled=cfg.openrouter.enable_structured_outputs,
    )

    interaction_id = await recorder.log(
        PreparedRouteContext(
            message=SimpleNamespace(),
            telegram_message=Mock(),
            text="hello",
            uid=42,
            chat_id=99,
            message_id=7,
            has_forward=True,
            forward_from_chat_id=555,
            forward_from_chat_title="Forwarded",
            forward_from_message_id=321,
            interaction_type="command",
            command="/start",
            first_url=None,
            media_type="text",
            correlation_id="cid-123",
        )
    )

    assert interaction_id > 0

    row = await session.scalar(
        select(UserInteraction).where(UserInteraction.id == interaction_id)
    )
    assert row is not None
    assert row.user_id == 42
    assert row.interaction_type == "command"
    assert row.command == "/start"
    assert row.has_forward is True
    assert row.structured_output_enabled is True
    assert row.correlation_id == "cid-123"


async def test_safe_update_user_interaction_updates_interaction(
    database: Database, session: AsyncSession
) -> None:
    user_repo = UserRepositoryAdapter(database)
    request_repo = RequestRepositoryAdapter(database)

    request_id = await request_repo.async_create_request(
        type_="url",
        status=RequestStatus.COMPLETED,
        correlation_id="test-corr-id",
        user_id=7,
        chat_id=11,
        normalized_url="https://example.com",
    )

    interaction_id = await user_repo.async_insert_user_interaction(
        user_id=7,
        interaction_type="command",
        chat_id=11,
        message_id=22,
        command="/help",
        input_text="help",
        structured_output_enabled=True,
    )

    safe_update_user_interaction(
        database,
        interaction_id=interaction_id,
        response_sent=True,
        response_type="help",
        error_occurred=True,
        error_message="boom",
        processing_time_ms=1234,
        request_id=request_id,
    )

    # safe_update_user_interaction returns synchronously but schedules the
    # actual UPDATE as a background task on the running loop. Wait for it
    # to settle before reading.
    import asyncio

    from app.db import user_interactions as _ui_mod

    pending = list(_ui_mod._update_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    row = await session.scalar(
        select(UserInteraction).where(UserInteraction.id == interaction_id)
    )
    assert row is not None
    assert row.response_sent is True
    assert row.response_type == "help"
    assert row.error_occurred is True
    assert row.error_message == "boom"
    assert row.processing_time_ms == 1234
    assert row.request_id == request_id


async def test_async_safe_update_user_interaction_updates_interaction(
    database: Database, session: AsyncSession
) -> None:
    user_repo = UserRepositoryAdapter(database)
    request_repo = RequestRepositoryAdapter(database)

    request_id = await request_repo.async_create_request(
        type_="url",
        status=RequestStatus.COMPLETED,
        correlation_id="test-async-corr-id",
        user_id=13,
        chat_id=44,
        normalized_url="https://example.org",
    )

    interaction_id = await user_repo.async_insert_user_interaction(
        user_id=13,
        interaction_type="url",
        chat_id=44,
        message_id=55,
        command="/summary",
        input_text="go",
        structured_output_enabled=False,
    )

    await async_safe_update_user_interaction(
        user_repo,
        interaction_id=interaction_id,
        response_sent=True,
        response_type="summary",
        error_occurred=False,
        error_message=None,
        request_id=request_id,
    )

    row = await session.scalar(
        select(UserInteraction).where(UserInteraction.id == interaction_id)
    )
    assert row is not None
    assert row.response_sent is True
    assert row.response_type == "summary"
    assert row.error_occurred is False
    assert row.error_message is None
    assert row.request_id == request_id
