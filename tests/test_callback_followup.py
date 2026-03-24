from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapter_models.llm.llm_models import LLMCallResult
from app.adapters.external.formatting.summary.action_buttons import create_action_buttons
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.routing.content_router import MessageContentRouter
from app.adapters.telegram.routing.interactions import MessageInteractionRecorder
from app.adapters.telegram.routing.models import PreparedRouteContext
from app.core.call_status import CallStatus


class _ResponseFormatterStub:
    def __init__(self) -> None:
        self.safe_reply = AsyncMock()
        self.send_error_notification = AsyncMock()
        self.send_topic_search_results = AsyncMock()
        self.send_russian_translation = AsyncMock()


@pytest.mark.asyncio
async def test_callback_ask_starts_followup_session() -> None:
    formatter = _ResponseFormatterStub()
    handler = CallbackHandler(
        db=MagicMock(),
        response_formatter=cast("Any", formatter),
        url_handler=None,
        hybrid_search=None,
        lang="en",
    )
    callback_query = SimpleNamespace(message=SimpleNamespace())

    cast("Any", handler._followup)._load_summary_payload = AsyncMock(
        return_value={"id": "42", "request_id": 100, "summary_250": "Short summary"}
    )

    handled = await handler.handle_callback(callback_query, uid=7, callback_data="ask:42")

    assert handled is True
    assert await handler.has_pending_followup(7) is True
    formatter.safe_reply.assert_awaited()
    sent_text = formatter.safe_reply.await_args.args[1]
    assert "follow-up" in sent_text.lower()


@pytest.mark.asyncio
async def test_followup_question_uses_llm_grounded_context() -> None:
    formatter = _ResponseFormatterStub()
    llm_client = SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMCallResult(
                status=CallStatus.OK,
                response_text="Answer based on the stored summary and source.",
                model="test/model",
            )
        )
    )
    url_handler = SimpleNamespace(
        _llm_client=llm_client,
    )
    handler = CallbackHandler(
        db=MagicMock(),
        response_formatter=cast("Any", formatter),
        url_handler=cast("Any", url_handler),
        hybrid_search=None,
        lang="en",
    )

    await handler._activate_followup_session(uid=9, summary_id="42")
    cast("Any", handler._followup)._load_summary_payload = AsyncMock(
        return_value={
            "id": "42",
            "request_id": 5,
            "url": "https://example.com/post",
            "lang": "en",
            "summary_250": "Compact summary",
            "summary_1000": "Extended summary",
            "metadata": {"title": "Example"},
        }
    )
    cast("Any", handler._followup)._load_source_context = MagicMock(
        return_value="Source excerpt from stored crawl."
    )

    handled = await handler.handle_followup_question(
        message=SimpleNamespace(),
        uid=9,
        question="What is the main claim?",
        correlation_id="cid-9",
    )

    assert handled is True
    llm_client.chat.assert_awaited_once()
    call_messages = llm_client.chat.await_args.args[0]
    assert "main claim" in call_messages[-1]["content"].lower()
    formatter.safe_reply.assert_awaited()
    sent_text = formatter.safe_reply.await_args.args[1]
    assert "stored summary and source" in sent_text
    assert await handler.has_pending_followup(9) is True


@pytest.mark.asyncio
async def test_action_buttons_include_followup_callback() -> None:
    buttons = create_action_buttons(summary_id=101, lang="en")
    callback_values = [btn["callback_data"] for row in buttons for btn in row]
    assert "ask:101" in callback_values


@pytest.mark.asyncio
async def test_message_router_prioritizes_followup_questions() -> None:
    command_processor = MagicMock()
    command_processor.has_active_init_session.return_value = False
    callback_handler = SimpleNamespace(
        has_pending_followup=AsyncMock(return_value=True),
        clear_pending_followup=AsyncMock(),
        handle_followup_question=AsyncMock(return_value=True),
    )
    response_formatter = _ResponseFormatterStub()
    router = MessageContentRouter(
        command_dispatcher=cast("Any", command_processor),
        url_handler=cast(
            "Any",
            SimpleNamespace(
                is_awaiting_url=AsyncMock(return_value=False),
                handle_awaited_url=AsyncMock(),
                handle_direct_url=AsyncMock(),
                handle_document_file=AsyncMock(),
                can_handle_document=MagicMock(return_value=False),
                add_awaiting_user=AsyncMock(),
            ),
        ),
        forward_processor=cast(
            "Any",
            SimpleNamespace(handle_forward_flow=AsyncMock()),
        ),
        response_formatter=cast("Any", response_formatter),
        interaction_recorder=MessageInteractionRecorder(
            user_repo=SimpleNamespace(async_insert_user_interaction=AsyncMock()),
            structured_output_enabled=True,
        ),
        callback_handler=cast("Any", callback_handler),
        attachment_processor=None,
        lang="en",
    )

    context = PreparedRouteContext(
        message=SimpleNamespace(
            contact=None,
            web_app_data=None,
            text="Can you clarify the timeline?",
            caption=None,
            photo=None,
            document=None,
            forward_from_chat=None,
        ),
        telegram_message=MagicMock(),
        text="Can you clarify the timeline?",
        uid=11,
        chat_id=100,
        message_id=55,
        has_forward=False,
        forward_from_chat_id=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        interaction_type="text",
        command=None,
        first_url=None,
        media_type=None,
        correlation_id="cid-11",
    )

    await router.route(context, interaction_id=0, start_time=0.0)

    callback_handler.handle_followup_question.assert_awaited_once()
    response_formatter.safe_reply.assert_not_awaited()
