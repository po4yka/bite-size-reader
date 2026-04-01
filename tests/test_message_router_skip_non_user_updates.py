from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.telegram.message_router import MessageRouter
from tests.conftest import make_test_app_config

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import (
        ResponseFormatterFacade as ResponseFormatter,
    )
    from app.adapters.telegram.access_controller import AccessController
    from app.adapters.telegram.url_handler import URLHandler


def _build_router() -> tuple[MessageRouter, SimpleNamespace, SimpleNamespace]:
    access_controller = SimpleNamespace(check_access=AsyncMock(return_value=True))
    response_formatter = SimpleNamespace(
        safe_reply=AsyncMock(),
        send_error_notification=AsyncMock(),
    )

    router = MessageRouter(
        cfg=make_test_app_config(),
        db=Mock(),
        access_controller=cast("AccessController", access_controller),
        command_processor=Mock(),
        url_handler=cast("URLHandler", SimpleNamespace(url_processor=Mock())),
        forward_processor=Mock(),
        response_formatter=cast("ResponseFormatter", response_formatter),
        audit_func=lambda *_args, **_kwargs: None,
    )
    return router, access_controller, response_formatter


@pytest.mark.asyncio
async def test_route_message_ignores_outgoing_message_updates() -> None:
    router, access_controller, response_formatter = _build_router()

    message = SimpleNamespace(
        outgoing=True,
        id=101,
        from_user=SimpleNamespace(id=123456789, is_bot=False),
        chat=SimpleNamespace(id=123456789),
        text="Digest item title",
    )

    await router.route_message(message)

    access_controller.check_access.assert_not_awaited()
    response_formatter.safe_reply.assert_not_awaited()
    response_formatter.send_error_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_message_ignores_bot_origin_messages() -> None:
    router, access_controller, response_formatter = _build_router()

    message = SimpleNamespace(
        outgoing=False,
        id=202,
        from_user=SimpleNamespace(id=123456789, is_bot=True),
        chat=SimpleNamespace(id=123456789),
        text="Any text",
    )

    await router.route_message(message)

    access_controller.check_access.assert_not_awaited()
    response_formatter.safe_reply.assert_not_awaited()
    response_formatter.send_error_notification.assert_not_awaited()
