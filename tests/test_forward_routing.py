from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.telegram.message_router import MessageRouter
from app.db.session import DatabaseSessionManager
from tests.conftest import make_test_app_config

if TYPE_CHECKING:
    from app.config import AppConfig


def _make_config() -> AppConfig:
    return make_test_app_config(db_path=":memory:")


def _make_db(tmp_path) -> DatabaseSessionManager:
    db = DatabaseSessionManager(str(tmp_path / "forward-routing.db"))
    db.migrate()
    return db


def _make_router(tmp_path):
    cfg = _make_config()
    db = _make_db(tmp_path)

    command_processor = Mock()
    command_processor.has_active_init_session.return_value = False
    url_handler: Any = SimpleNamespace(
        url_processor=Mock(),
        is_awaiting_url=AsyncMock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_document_file=AsyncMock(),
        can_handle_document=Mock(return_value=False),
        add_awaiting_user=AsyncMock(),
    )
    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())
    attachment_processor: Any = SimpleNamespace(handle_attachment_flow=AsyncMock())
    aggregation_handler: Any = SimpleNamespace(handle_message_bundle=AsyncMock())
    response_formatter: Any = SimpleNamespace(
        safe_reply=AsyncMock(),
        send_error_notification=AsyncMock(),
    )

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=SimpleNamespace(check_access=AsyncMock(return_value=True)),
        command_processor=command_processor,
        url_handler=url_handler,
        forward_processor=forward_processor,
        attachment_processor=attachment_processor,
        aggregation_handler=aggregation_handler,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )
    return (
        router,
        forward_processor,
        attachment_processor,
        aggregation_handler,
        response_formatter,
        url_handler,
    )


def _base_message(**overrides: Any) -> SimpleNamespace:
    payload = {
        "id": 44,
        "chat": SimpleNamespace(id=9001),
        "from_user": SimpleNamespace(id=1, is_bot=False),
        "contact": None,
        "web_app_data": None,
        "document": None,
        "photo": None,
        "outgoing": False,
        "caption": None,
        "forward_from": None,
        "forward_from_chat": None,
        "forward_from_message_id": None,
        "forward_sender_name": None,
        "forward_date": None,
        "text": "",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_forward_message_with_url_prefers_aggregation_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        _attachment_processor,
        aggregation_handler,
        _response_formatter,
        url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        text="https://example.com/article",
        forward_from_chat=SimpleNamespace(id=-100200300, title="Forwarded Channel"),
        forward_from_message_id=123,
        forward_date=1700000000,
    )

    await router.route_message(message)

    aggregation_handler.handle_message_bundle.assert_awaited_once_with(
        message=message,
        text="https://example.com/article",
        uid=1,
        correlation_id=aggregation_handler.handle_message_bundle.await_args.kwargs[
            "correlation_id"
        ],
        interaction_id=aggregation_handler.handle_message_bundle.await_args.kwargs[
            "interaction_id"
        ],
    )
    forward_processor.handle_forward_flow.assert_not_awaited()
    url_handler.handle_direct_url.assert_not_awaited()
    url_handler.handle_awaited_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_from_user_with_text_routes_to_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        _attachment_processor,
        _aggregation_handler,
        _response_formatter,
        url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        text="Some interesting article content",
        forward_from=SimpleNamespace(id=12345, first_name="John", last_name="Doe"),
        forward_date=1700000000,
    )

    await router.route_message(message)

    forward_processor.handle_forward_flow.assert_awaited_once()
    url_handler.handle_direct_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_privacy_protected_with_text_routes_to_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        _attachment_processor,
        _aggregation_handler,
        _response_formatter,
        url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        text="Privacy protected forward content",
        forward_sender_name="Hidden User",
        forward_date=1700000000,
    )

    await router.route_message(message)

    forward_processor.handle_forward_flow.assert_awaited_once()
    url_handler.handle_direct_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_from_user_no_text_shows_error(tmp_path, tmp_path_factory, request) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        _attachment_processor,
        _aggregation_handler,
        response_formatter,
        _url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        text=None,
        forward_from=SimpleNamespace(id=12345, first_name="John", last_name="Doe"),
        forward_date=1700000000,
    )

    await router.route_message(message)

    forward_processor.handle_forward_flow.assert_not_awaited()
    response_formatter.safe_reply.assert_awaited_once()
    reply_text = response_formatter.safe_reply.call_args[0][1]
    assert "no text content" in reply_text.lower()


@pytest.mark.asyncio
async def test_forwarded_channel_photo_with_caption_prefers_attachment_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        attachment_processor,
        _aggregation_handler,
        _response_formatter,
        _url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        caption="Forwarded photo caption",
        photo=[SimpleNamespace(file_id="photo-1")],
        forward_from_chat=SimpleNamespace(id=-100200300, title="Forwarded Channel"),
        forward_from_message_id=123,
        forward_date=1700000000,
    )

    await router.route_message(message)

    attachment_processor.handle_attachment_flow.assert_awaited_once()
    forward_processor.handle_forward_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_from_user_photo_with_caption_prefers_attachment_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        attachment_processor,
        _aggregation_handler,
        _response_formatter,
        _url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        caption="Forwarded photo caption",
        photo=[SimpleNamespace(file_id="photo-1")],
        forward_from=SimpleNamespace(id=12345, first_name="John", last_name="Doe"),
        forward_date=1700000000,
    )

    await router.route_message(message)

    attachment_processor.handle_attachment_flow.assert_awaited_once()
    forward_processor.handle_forward_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_forward_message_with_multiple_urls_routes_via_aggregation_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory, request
    (
        router,
        forward_processor,
        attachment_processor,
        aggregation_handler,
        _response_formatter,
        url_handler,
    ) = _make_router(tmp_path)

    message = _base_message(
        text="https://example.com/a https://example.com/b",
        forward_from_chat=SimpleNamespace(id=-100200300, title="Forwarded Channel"),
        forward_from_message_id=123,
        forward_date=1700000000,
    )

    await router.route_message(message)

    aggregation_handler.handle_message_bundle.assert_awaited_once()
    forward_processor.handle_forward_flow.assert_not_awaited()
    attachment_processor.handle_attachment_flow.assert_not_awaited()
    url_handler.handle_direct_url.assert_not_awaited()
