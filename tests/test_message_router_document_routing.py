from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.message_router_content import MessageRouterContentMixin


class _DummyRouter(MessageRouterContentMixin):
    _lang = "en"

    def __init__(self) -> None:
        self.url_handler = SimpleNamespace(
            can_handle_document=MagicMock(return_value=True),
            handle_document_file=AsyncMock(),
            is_awaiting_url=AsyncMock(return_value=False),
        )
        self.response_formatter = SimpleNamespace(safe_reply=AsyncMock())
        self.command_processor = SimpleNamespace(
            has_active_init_session=MagicMock(return_value=False)
        )
        self.forward_processor = None
        self.attachment_processor = None
        self.callback_handler = None
        self.user_repo = SimpleNamespace()
        self._should_handle_attachment = MagicMock(return_value=False)

    async def _route_command_message(self, *args, **kwargs) -> bool:
        return False

    async def _route_forward_message(self, *args, **kwargs) -> bool:
        return False


@pytest.mark.asyncio
async def test_txt_documents_are_routed_via_url_handler() -> None:
    router = _DummyRouter()
    message = SimpleNamespace(
        document=SimpleNamespace(file_name="batch.txt"),
        contact=None,
        web_app_data=None,
    )

    await router._route_message_content(
        message=message,
        text="",
        uid=1,
        has_forward=False,
        correlation_id="cid",
        interaction_id=10,
        start_time=0.0,
    )

    router.url_handler.can_handle_document.assert_called_once_with(message)
    router.url_handler.handle_document_file.assert_awaited_once_with(
        message,
        "cid",
        10,
        0.0,
    )
