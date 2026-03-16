from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.external.formatting.summary_presenter_parts.actions import create_action_buttons
from app.adapters.telegram.callback_handler import CallbackHandler
from app.adapters.telegram.message_router_content import MessageRouterContentMixin
from app.models.llm.llm_models import LLMCallResult


class _ResponseFormatterStub:
    def __init__(self) -> None:
        self.sender = SimpleNamespace(safe_reply=AsyncMock())
        self.notifications = SimpleNamespace(send_error_notification=AsyncMock())
        self.database = SimpleNamespace(send_topic_search_results=AsyncMock())
        self.summaries = SimpleNamespace(send_russian_translation=AsyncMock())
        self.safe_reply = AsyncMock()


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
    formatter.sender.safe_reply.assert_awaited()
    sent_text = formatter.sender.safe_reply.await_args.args[1]
    assert "follow-up" in sent_text.lower()


@pytest.mark.asyncio
async def test_followup_question_uses_llm_grounded_context() -> None:
    formatter = _ResponseFormatterStub()
    llm_client = SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMCallResult(
                status="ok",
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
    cast("Any", handler._followup)._load_source_context = AsyncMock(
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
    formatter.sender.safe_reply.assert_awaited()
    sent_text = formatter.sender.safe_reply.await_args.args[1]
    assert "stored summary and source" in sent_text
    assert await handler.has_pending_followup(9) is True


@pytest.mark.asyncio
async def test_action_buttons_include_followup_callback() -> None:
    buttons = create_action_buttons(summary_id=101, lang="en")
    callback_values = [btn["callback_data"] for row in buttons for btn in row]
    assert "ask:101" in callback_values


@pytest.mark.asyncio
async def test_message_router_prioritizes_followup_questions() -> None:
    class _DummyRouter(MessageRouterContentMixin):
        pass

    router = _DummyRouter()
    router._lang = "en"
    router._should_handle_attachment = lambda _msg: False
    router.attachment_processor = None
    router.command_processor = SimpleNamespace(has_active_init_session=lambda _uid: False)
    cast("Any", router)._route_command_message = AsyncMock(return_value=False)
    cast("Any", router)._route_forward_message = AsyncMock(return_value=False)
    router.url_handler = SimpleNamespace(
        is_awaiting_url=AsyncMock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
    )
    router.response_formatter = _ResponseFormatterStub()
    router.callback_handler = SimpleNamespace(
        has_pending_followup=AsyncMock(return_value=True),
        clear_pending_followup=AsyncMock(),
        handle_followup_question=AsyncMock(return_value=True),
    )
    router.user_repo = MagicMock()

    message = SimpleNamespace(
        contact=None,
        web_app_data=None,
        text="Can you clarify the timeline?",
        caption=None,
    )

    await router._route_message_content(
        message=message,
        text="Can you clarify the timeline?",
        uid=11,
        has_forward=False,
        correlation_id="cid-11",
        interaction_id=0,
        start_time=0.0,
    )

    router.callback_handler.handle_followup_question.assert_awaited_once()
    router.response_formatter.safe_reply.assert_not_awaited()
