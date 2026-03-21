from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from app.adapters.telegram.message_handler import MessageHandler
from tests.conftest import make_test_app_config


class _ResponseFormatterStub:
    def __init__(self) -> None:
        self._lang = "en"
        self.safe_reply = AsyncMock()
        self.send_error_notification = AsyncMock()
        self.sender = SimpleNamespace(safe_reply=AsyncMock())
        self.notifications = SimpleNamespace(send_error_notification=AsyncMock())
        self.database = SimpleNamespace(send_topic_search_results=AsyncMock())
        self.summaries = SimpleNamespace(send_russian_translation=AsyncMock())


def test_message_handler_wires_callback_handler_during_construction(tmp_path) -> None:
    callback_handler = SimpleNamespace(handle_callback=AsyncMock())
    message_router = SimpleNamespace(
        callback_handler=callback_handler,
        route_message=AsyncMock(),
    )

    handler = MessageHandler(
        cfg=make_test_app_config(db_path=":memory:"),
        db=None,
        audit_repo=None,
        task_manager=None,
        access_controller=cast("Any", SimpleNamespace()),
        url_handler=cast("Any", SimpleNamespace(url_processor=SimpleNamespace())),
        command_dispatcher=cast("Any", SimpleNamespace()),
        callback_handler=cast("Any", callback_handler),
        message_router=cast("Any", message_router),
    )

    assert handler.message_router.callback_handler is handler.callback_handler
