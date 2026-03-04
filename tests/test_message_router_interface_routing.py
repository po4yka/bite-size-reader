from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.message_router_content import MessageRouterContentMixin
from app.migration.telegram_runtime import TelegramRuntimeCommandDecision


class _Router(MessageRouterContentMixin):
    def __init__(self) -> None:
        self.command_processor = MagicMock()
        self.command_processor.handle_find_online_command = AsyncMock()
        self.command_processor.handle_find_local_command = AsyncMock()
        self.command_processor.handle_start_command = AsyncMock()
        self.command_processor.handle_help_command = AsyncMock()
        self.command_processor.handle_dbinfo_command = AsyncMock()
        self.command_processor.handle_dbverify_command = AsyncMock()
        self.command_processor.handle_clearcache_command = AsyncMock()
        self.command_processor.handle_summarize_all_command = AsyncMock()
        self.command_processor.handle_summarize_command = AsyncMock(return_value=("ok", True))
        self.command_processor.handle_cancel_command = AsyncMock()
        self.command_processor.handle_unread_command = AsyncMock()
        self.command_processor.handle_read_command = AsyncMock()
        self.command_processor.handle_search_command = AsyncMock()
        self.command_processor.handle_sync_karakeep_command = AsyncMock()
        self.command_processor.handle_cdigest_command = AsyncMock()
        self.command_processor.handle_digest_command = AsyncMock()
        self.command_processor.handle_channels_command = AsyncMock()
        self.command_processor.handle_subscribe_command = AsyncMock()
        self.command_processor.handle_unsubscribe_command = AsyncMock()
        self.command_processor.handle_init_session_command = AsyncMock()
        self.command_processor.handle_settings_command = AsyncMock()
        self.command_processor.handle_debug_command = AsyncMock()

        self.url_handler = MagicMock()
        self.url_handler.add_awaiting_user = AsyncMock()
        self.telegram_runtime_runner = MagicMock()
        self.response_formatter = MagicMock()
        self.user_repo = MagicMock()
        self._lang = "en"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_alias_for_handler_payload() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline rust migration",
        uid=1,
        correlation_id="cid-1",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/findonline ")
    assert call.kwargs["command"] == "/findonline"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_alias_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@mybot rust migration",
        uid=11,
        correlation_id="cid-11",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/findonline@mybot ")
    assert call.kwargs["command"] == "/findonline"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_local_alias_for_handler_payload() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/finddb", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findlocal rust migration",
        uid=2,
        correlation_id="cid-2",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_local_command.assert_called_once()
    call = router.command_processor.handle_find_local_command.call_args
    assert call.args[1].startswith("/findlocal ")
    assert call.kwargs["command"] == "/findlocal"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_local_alias_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/finddb", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findlocal@mybot rust migration",
        uid=12,
        correlation_id="cid-12",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_local_command.assert_called_once()
    call = router.command_processor.handle_find_local_command.call_args
    assert call.args[1].startswith("/findlocal@mybot ")
    assert call.kwargs["command"] == "/findlocal"


@pytest.mark.asyncio
async def test_route_command_message_marks_awaiting_user_for_summarize_prompt() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/summarize", handled=True)
    )
    router.command_processor.handle_summarize_command = AsyncMock(
        return_value=("awaiting_url", True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/summarize",
        uid=3,
        correlation_id="cid-3",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_summarize_command.assert_called_once()
    router.url_handler.add_awaiting_user.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_route_command_message_marks_awaiting_user_for_summarize_prompt_with_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/summarize", handled=True)
    )
    router.command_processor.handle_summarize_command = AsyncMock(
        return_value=("awaiting_url", True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/summarize@mybot",
        uid=13,
        correlation_id="cid-13",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_summarize_command.assert_called_once()
    call = router.command_processor.handle_summarize_command.call_args
    assert call.args[1] == "/summarize@mybot"
    router.url_handler.add_awaiting_user.assert_awaited_once_with(13)


@pytest.mark.asyncio
async def test_route_command_message_routes_cancel_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/cancel", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/cancel@mybot",
        uid=14,
        correlation_id="cid-14",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_cancel_command.assert_awaited_once()
    call = router.command_processor.handle_cancel_command.call_args
    assert call.args[1:] == (14, "cid-14", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_requires_telegram_runtime_runner() -> None:
    router = _Router()
    delattr(router, "telegram_runtime_runner")

    with pytest.raises(RuntimeError, match="fallback is decommissioned"):
        await router._route_command_message(
            message=SimpleNamespace(),
            text="/start",
            uid=1,
            correlation_id="cid-missing-runner",
            interaction_id=0,
            start_time=0.0,
        )
