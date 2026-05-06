from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from app.adapters.telegram.routing.interactions import MessageInteractionRecorder
from app.adapters.telegram.routing.models import PreparedRouteContext
from app.config import AppConfig  # noqa: TC001 - used for type annotation
try:
    from app.db.session import DatabaseSessionManager  # type: ignore[attr-defined]
except ImportError:
    DatabaseSessionManager = None  # type: ignore[assignment,misc]
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
    from collections.abc import Generator


def _make_config() -> AppConfig:
    return make_test_app_config(db_path=":memory:")


@pytest.fixture
def db(tmp_path) -> Generator[DatabaseSessionManager]:
    from app.db.models import database_proxy

    # Save the original database proxy state
    old_db = database_proxy.obj

    # Create test database with file-based storage
    db_instance = DatabaseSessionManager(str(tmp_path / "interactions.db"))
    db_instance.migrate()

    # Ensure database_proxy is initialized AFTER migrate
    database_proxy.initialize(db_instance._database)

    yield db_instance

    # Close the database and restore original proxy
    db_instance._database.close()
    database_proxy.initialize(old_db)


def test_message_router_logs_interaction(db: DatabaseSessionManager) -> None:
    cfg = _make_config()
    recorder = MessageInteractionRecorder(
        user_repo=UserRepositoryAdapter(db),
        structured_output_enabled=cfg.openrouter.enable_structured_outputs,
    )

    interaction_id = asyncio.run(
        recorder.log(
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
    )

    assert interaction_id > 0

    row = db.fetchone("SELECT * FROM user_interactions WHERE id = ?", (interaction_id,))
    assert row is not None
    assert row["user_id"] == 42
    assert row["interaction_type"] == "command"
    assert row["command"] == "/start"
    assert row["has_forward"] == 1
    assert row["structured_output_enabled"] == 1
    assert row["correlation_id"] == "cid-123"


def test_safe_update_user_interaction_updates_interaction(db: DatabaseSessionManager) -> None:
    user_repo = UserRepositoryAdapter(db)
    request_repo = RequestRepositoryAdapter(db)

    # Create a request first (required for foreign key constraint)
    request_id = asyncio.run(
        request_repo.async_create_request(
            type_="url",
            status=RequestStatus.COMPLETED,
            correlation_id="test-corr-id",
            user_id=7,
            chat_id=11,
            normalized_url="https://example.com",
        )
    )

    interaction_id = asyncio.run(
        user_repo.async_insert_user_interaction(
            user_id=7,
            interaction_type="command",
            chat_id=11,
            message_id=22,
            command="/help",
            input_text="help",
            structured_output_enabled=True,
        )
    )

    safe_update_user_interaction(
        db,
        interaction_id=interaction_id,
        response_sent=True,
        response_type="help",
        error_occurred=True,
        error_message="boom",
        processing_time_ms=1234,
        request_id=request_id,
    )

    # Wait for background task if any (safe_update_user_interaction might spawn one)
    # But since it's sync helper in test, it might be tricky.
    # The sync helper uses loop.create_task if loop is running.
    # In this test, no loop is running in the main thread during safe_update_user_interaction call?
    # Wait, safe_update_user_interaction has loop detection.

    row = db.fetchone(
        "SELECT response_sent, response_type, error_occurred, error_message, processing_time_ms, request_id "
        "FROM user_interactions WHERE id = ?",
        (interaction_id,),
    )

    assert row is not None
    assert row["response_sent"] == 1
    assert row["response_type"] == "help"
    assert row["error_occurred"] == 1
    assert row["error_message"] == "boom"
    assert row["processing_time_ms"] == 1234
    assert row["request_id"] == request_id


def test_async_safe_update_user_interaction_updates_interaction(db: DatabaseSessionManager) -> None:
    user_repo = UserRepositoryAdapter(db)
    request_repo = RequestRepositoryAdapter(db)

    # Create a request first (required for foreign key constraint)
    request_id = asyncio.run(
        request_repo.async_create_request(
            type_="url",
            status=RequestStatus.COMPLETED,
            correlation_id="test-async-corr-id",
            user_id=13,
            chat_id=44,
            normalized_url="https://example.org",
        )
    )

    interaction_id = asyncio.run(
        user_repo.async_insert_user_interaction(
            user_id=13,
            interaction_type="url",
            chat_id=44,
            message_id=55,
            command="/summary",
            input_text="go",
            structured_output_enabled=False,
        )
    )

    asyncio.run(
        async_safe_update_user_interaction(
            user_repo,
            interaction_id=interaction_id,
            response_sent=True,
            response_type="summary",
            error_occurred=False,
            error_message=None,
            request_id=request_id,
        )
    )

    row = db.fetchone(
        "SELECT response_sent, response_type, error_occurred, error_message, request_id "
        "FROM user_interactions WHERE id = ?",
        (interaction_id,),
    )

    assert row is not None
    assert row["response_sent"] == 1
    assert row["response_type"] == "summary"
    assert row["error_occurred"] == 0
    assert row["error_message"] is None
    assert row["request_id"] == request_id
