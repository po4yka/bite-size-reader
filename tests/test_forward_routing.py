from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.telegram.message_router import MessageRouter
from app.config import AppConfig
from app.db.database import Database
from tests.conftest import make_test_app_config


def _make_config() -> AppConfig:
    return make_test_app_config(db_path=":memory:")


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "forward-routing.db"))
    db.migrate()
    return db


@pytest.mark.asyncio
async def test_forward_message_with_url_prefers_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory
    del request
    cfg = _make_config()
    db = _make_db(tmp_path)

    access_controller: Any = SimpleNamespace(check_access=AsyncMock(return_value=True))

    command_processor = Mock()

    url_handler: Any = SimpleNamespace(
        url_processor=Mock(),
        is_awaiting_url=Mock(return_value=False),
        has_pending_multi_links=Mock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_multi_link_confirmation=AsyncMock(),
        add_pending_multi_links=Mock(),
        add_awaiting_user=Mock(),
    )

    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())

    response_formatter: Any = SimpleNamespace(safe_reply=AsyncMock())

    router = MessageRouter(
        cfg=cfg,
        db=db,  # type: ignore[arg-type]
        access_controller=access_controller,
        command_processor=command_processor,
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )

    message = SimpleNamespace(
        text="https://example.com/article",
        forward_from_chat=SimpleNamespace(id=-100200300, title="Forwarded Channel"),
        forward_from_message_id=123,
    )

    await router._route_message_content(
        message,
        text=message.text,
        uid=1,
        has_forward=True,
        correlation_id="cid-1",
        interaction_id=99,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_awaited_once_with(
        message, correlation_id="cid-1", interaction_id=99
    )
    url_handler.handle_direct_url.assert_not_awaited()
    url_handler.handle_awaited_url.assert_not_awaited()


def _make_router(tmp_path):
    """Build a MessageRouter with standard mocks for routing tests."""
    cfg = _make_config()
    db = _make_db(tmp_path)

    url_handler: Any = SimpleNamespace(
        url_processor=Mock(),
        is_awaiting_url=Mock(return_value=False),
        has_pending_multi_links=Mock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_multi_link_confirmation=AsyncMock(),
        add_pending_multi_links=Mock(),
        add_awaiting_user=Mock(),
    )
    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())
    response_formatter: Any = SimpleNamespace(safe_reply=AsyncMock())

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=SimpleNamespace(check_access=AsyncMock(return_value=True)),
        command_processor=Mock(),
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )
    return router, forward_processor, response_formatter, url_handler


@pytest.mark.asyncio
async def test_forward_from_user_with_text_routes_to_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    """Forward from a user (not channel) with text should be processed as forward."""
    del tmp_path_factory, request
    router, forward_processor, _response_formatter, url_handler = _make_router(tmp_path)

    message = SimpleNamespace(
        text="Some interesting article content",
        forward_from=SimpleNamespace(id=12345, first_name="John", last_name="Doe"),
        forward_from_chat=None,
        forward_from_message_id=None,
        forward_sender_name=None,
        forward_date=1700000000,
    )

    await router._route_message_content(
        message,
        text=message.text,
        uid=1,
        has_forward=True,
        correlation_id="cid-2",
        interaction_id=100,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_awaited_once()
    url_handler.handle_direct_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_privacy_protected_with_text_routes_to_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    """Forward from a privacy-protected user (forward_sender_name only) should be processed."""
    del tmp_path_factory, request
    router, forward_processor, _response_formatter, url_handler = _make_router(tmp_path)

    message = SimpleNamespace(
        text="Privacy protected forward content",
        forward_from=None,
        forward_from_chat=None,
        forward_from_message_id=None,
        forward_sender_name="Hidden User",
        forward_date=1700000000,
    )

    await router._route_message_content(
        message,
        text=message.text,
        uid=1,
        has_forward=True,
        correlation_id="cid-3",
        interaction_id=101,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_awaited_once()
    url_handler.handle_direct_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_from_user_no_text_shows_error(tmp_path, tmp_path_factory, request) -> None:
    """Forward from a user with no text (media-only) should show explicit error."""
    del tmp_path_factory, request
    router, forward_processor, response_formatter, _url_handler = _make_router(tmp_path)

    message = SimpleNamespace(
        text=None,
        caption=None,
        forward_from=SimpleNamespace(id=12345, first_name="John", last_name="Doe"),
        forward_from_chat=None,
        forward_from_message_id=None,
        forward_sender_name=None,
        forward_date=1700000000,
    )

    await router._route_message_content(
        message,
        text="",
        uid=1,
        has_forward=True,
        correlation_id="cid-4",
        interaction_id=102,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_not_awaited()
    response_formatter.safe_reply.assert_awaited_once()
    reply_text = response_formatter.safe_reply.call_args[0][1]
    assert "no text content" in reply_text.lower()
