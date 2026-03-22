from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.routing.content_router import MessageContentRouter
from app.adapters.telegram.routing.interactions import MessageInteractionRecorder
from app.adapters.telegram.routing.models import PreparedRouteContext


def _make_context(message: SimpleNamespace) -> PreparedRouteContext:
    return PreparedRouteContext(
        message=message,
        telegram_message=MagicMock(),
        text="",
        uid=1,
        chat_id=100,
        message_id=10,
        has_forward=False,
        forward_from_chat_id=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        interaction_type="text",
        command=None,
        first_url=None,
        media_type=None,
        correlation_id="cid",
    )


@pytest.mark.asyncio
async def test_txt_documents_are_routed_via_url_handler() -> None:
    command_processor = MagicMock()
    command_processor.has_active_init_session.return_value = False
    url_handler = SimpleNamespace(
        can_handle_document=MagicMock(return_value=True),
        handle_document_file=AsyncMock(),
        is_awaiting_url=AsyncMock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        add_awaiting_user=AsyncMock(),
    )
    router = MessageContentRouter(
        command_dispatcher=cast("Any", command_processor),
        url_handler=cast("Any", url_handler),
        forward_processor=cast(
            "Any",
            SimpleNamespace(handle_forward_flow=AsyncMock()),
        ),
        response_formatter=cast(
            "Any",
            SimpleNamespace(safe_reply=AsyncMock()),
        ),
        interaction_recorder=MessageInteractionRecorder(
            user_repo=SimpleNamespace(async_insert_user_interaction=AsyncMock()),
            structured_output_enabled=True,
        ),
        callback_handler=None,
        attachment_processor=None,
        lang="en",
    )
    message = SimpleNamespace(
        document=SimpleNamespace(file_name="batch.txt"),
        contact=None,
        web_app_data=None,
        photo=None,
        text=None,
        caption=None,
    )

    await router.route(_make_context(message), interaction_id=10, start_time=0.0)

    url_handler.can_handle_document.assert_called_once_with(message)
    url_handler.handle_document_file.assert_awaited_once_with(
        message,
        "cid",
        10,
        0.0,
    )
