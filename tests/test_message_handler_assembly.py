from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from app.adapters.telegram.message_handler import MessageHandler
from app.db.session import DatabaseSessionManager
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
    response_formatter = _ResponseFormatterStub()
    url_processor = SimpleNamespace(summary_repo=None, audit_func=None)
    forward_processor = SimpleNamespace(handle_forward_flow=AsyncMock())
    db = DatabaseSessionManager(str(tmp_path / "assembly.db"))
    db.migrate()

    handler = MessageHandler(
        cfg=make_test_app_config(db_path=":memory:"),
        db=db,
        response_formatter=cast("Any", response_formatter),
        url_processor=cast("Any", url_processor),
        forward_processor=cast("Any", forward_processor),
    )

    assert handler.message_router.callback_handler is handler.callback_handler
