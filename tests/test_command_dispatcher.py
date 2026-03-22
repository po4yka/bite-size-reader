from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.command_dispatch import (
    CommandContextFactory,
    TelegramCommandRoutes,
    TelegramCommandRuntimeState,
    TextCommandRoute,
    UidCommandRoute,
)
from app.adapters.telegram.command_dispatcher import TelegramCommandDispatcher


def _make_dispatcher(
    *,
    routes: TelegramCommandRoutes | None = None,
    runtime_state: TelegramCommandRuntimeState | None = None,
    summarize_result: tuple[str | None, bool] = (None, False),
) -> TelegramCommandDispatcher:
    runtime_state = runtime_state or TelegramCommandRuntimeState(
        url_processor=MagicMock(),
        url_handler=SimpleNamespace(add_awaiting_user=AsyncMock()),
        topic_searcher=MagicMock(),
        local_searcher=MagicMock(),
        _task_manager=MagicMock(),
        hybrid_search=MagicMock(),
    )
    routes = routes or TelegramCommandRoutes(
        pre_alias_uid=(),
        pre_alias_text=(),
        local_search_aliases=(),
        online_search_aliases=(),
        pre_summarize_text=(),
        summarize_prefix="/summarize",
        post_summarize_uid=(),
        post_summarize_text=(),
        tail_uid=(),
    )
    return TelegramCommandDispatcher(
        routes=routes,
        runtime_state=runtime_state,
        context_factory=CommandContextFactory(
            user_repo=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=MagicMock(),
        ),
        onboarding_handler=cast("Any", SimpleNamespace()),
        admin_handler=cast("Any", SimpleNamespace()),
        url_commands_handler=cast(
            "Any",
            SimpleNamespace(handle_summarize=AsyncMock(return_value=summarize_result)),
        ),
        content_handler=cast("Any", SimpleNamespace()),
        search_handler=cast("Any", SimpleNamespace()),
        listen_handler=cast("Any", SimpleNamespace()),
        digest_handler=cast("Any", SimpleNamespace()),
        init_session_handler=cast(
            "Any",
            SimpleNamespace(
                handle_contact=AsyncMock(),
                handle_web_app_data=AsyncMock(),
                has_active_session=lambda uid: uid == 7,
            ),
        ),
        settings_handler=cast("Any", SimpleNamespace()),
        tag_handler=cast("Any", SimpleNamespace()),
        rules_handler=cast("Any", SimpleNamespace()),
        export_handler=cast("Any", SimpleNamespace()),
        backup_handler=cast("Any", SimpleNamespace()),
    )


@pytest.mark.asyncio
async def test_dispatch_command_short_circuits_before_summarize() -> None:
    calls: list[str] = []

    async def handle_start(
        message: object,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        _ = (message, uid, correlation_id, interaction_id, start_time)
        calls.append("start")

    async def handle_post(
        message: object,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        _ = (message, text, uid, correlation_id, interaction_id, start_time)
        calls.append("post")

    routes = TelegramCommandRoutes(
        pre_alias_uid=(UidCommandRoute("/start", handle_start),),
        pre_alias_text=(),
        local_search_aliases=(),
        online_search_aliases=(),
        pre_summarize_text=(),
        summarize_prefix="/summarize",
        post_summarize_uid=(),
        post_summarize_text=(TextCommandRoute("/start", handle_post),),
        tail_uid=(),
    )
    dispatcher = _make_dispatcher(routes=routes)

    outcome = await dispatcher.dispatch_command(
        message=object(),
        text="/start",
        uid=1,
        correlation_id="cid",
        interaction_id=11,
        start_time=1.0,
    )

    assert outcome.handled is True
    assert calls == ["start"]


@pytest.mark.asyncio
async def test_dispatch_command_marks_awaiting_user_for_summarize_prompt() -> None:
    url_handler = SimpleNamespace(add_awaiting_user=AsyncMock())
    dispatcher = _make_dispatcher(
        runtime_state=TelegramCommandRuntimeState(
            url_processor=MagicMock(),
            url_handler=url_handler,
            topic_searcher=None,
            local_searcher=None,
            _task_manager=None,
            hybrid_search=None,
        ),
        summarize_result=("awaiting_url", False),
    )

    outcome = await dispatcher.dispatch_command(
        message=object(),
        text="/summarize",
        uid=42,
        correlation_id="cid",
        interaction_id=99,
        start_time=1.0,
    )

    assert outcome.handled is True
    assert outcome.next_action == "awaiting_url"
    url_handler.add_awaiting_user.assert_awaited_once_with(42)


def test_runtime_state_property_passthroughs_mutate_shared_state() -> None:
    state = TelegramCommandRuntimeState(
        url_processor=MagicMock(),
        url_handler=MagicMock(),
        topic_searcher=MagicMock(),
        local_searcher=MagicMock(),
        _task_manager=MagicMock(),
        hybrid_search=MagicMock(),
    )
    dispatcher = _make_dispatcher(runtime_state=state)

    new_url_processor = MagicMock()
    new_url_handler = MagicMock()
    new_topic_searcher = MagicMock()
    new_local_searcher = MagicMock()
    new_task_manager = MagicMock()
    new_hybrid_search = MagicMock()

    dispatcher.url_processor = new_url_processor
    dispatcher.url_handler = new_url_handler
    dispatcher.topic_searcher = new_topic_searcher
    dispatcher.local_searcher = new_local_searcher
    dispatcher._task_manager = new_task_manager
    dispatcher.hybrid_search = new_hybrid_search

    assert state.url_processor is new_url_processor
    assert state.url_handler is new_url_handler
    assert state.topic_searcher is new_topic_searcher
    assert state.local_searcher is new_local_searcher
    assert state._task_manager is new_task_manager
    assert state.hybrid_search is new_hybrid_search
