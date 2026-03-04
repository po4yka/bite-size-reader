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
async def test_route_command_message_preserves_original_alias_with_mixed_case_bot_username() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@MyBot rust migration",
        uid=37,
        correlation_id="cid-37",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/findonline@MyBot ")
    assert call.kwargs["command"] == "/findonline"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_alias_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@ rust migration",
        uid=38,
        correlation_id="cid-38",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/findonline@ ")
    assert call.kwargs["command"] == "/findonline"


@pytest.mark.asyncio
async def test_route_command_message_preserves_legacy_alias_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findweb@mybot rust migration",
        uid=18,
        correlation_id="cid-18",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/findweb@mybot ")
    assert call.kwargs["command"] == "/findweb"


@pytest.mark.asyncio
async def test_route_command_message_preserves_canonical_find_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@mybot rust migration",
        uid=19,
        correlation_id="cid-19",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/find@mybot ")
    assert call.kwargs["command"] == "/find"


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
async def test_route_command_message_preserves_canonical_local_search_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/finddb", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/finddb@mybot rust migration",
        uid=26,
        correlation_id="cid-26",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_local_command.assert_called_once()
    call = router.command_processor.handle_find_local_command.call_args
    assert call.args[1].startswith("/finddb@mybot ")
    assert call.kwargs["command"] == "/finddb"


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
async def test_route_command_message_routes_start_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/start", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/start@mybot",
        uid=16,
        correlation_id="cid-16",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_start_command.assert_awaited_once()
    call = router.command_processor.handle_start_command.call_args
    assert call.args[1:] == (16, "cid-16", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_help_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/help", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/help@mybot",
        uid=17,
        correlation_id="cid-17",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_help_command.assert_awaited_once()
    call = router.command_processor.handle_help_command.call_args
    assert call.args[1:] == (17, "cid-17", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_dbinfo_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/dbinfo", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/dbinfo@mybot",
        uid=23,
        correlation_id="cid-23",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_dbinfo_command.assert_awaited_once()
    call = router.command_processor.handle_dbinfo_command.call_args
    assert call.args[1:] == (23, "cid-23", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_dbverify_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/dbverify", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/dbverify@mybot",
        uid=24,
        correlation_id="cid-24",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_dbverify_command.assert_awaited_once()
    call = router.command_processor.handle_dbverify_command.call_args
    assert call.args[1:] == (24, "cid-24", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_clearcache_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/clearcache", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/clearcache@mybot",
        uid=25,
        correlation_id="cid-25",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_clearcache_command.assert_awaited_once()
    call = router.command_processor.handle_clearcache_command.call_args
    assert call.args[1:] == (25, "cid-25", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_search_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/search", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/search@mybot rust migration",
        uid=15,
        correlation_id="cid-15",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_search_command.assert_awaited_once()
    call = router.command_processor.handle_search_command.call_args
    assert call.args[1] == "/search@mybot rust migration"
    assert call.args[2:] == (15, "cid-15", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_summarize_all_with_bot_mention_and_preserves_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/summarize_all", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/summarize_all@mybot",
        uid=20,
        correlation_id="cid-20",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_summarize_all_command.assert_awaited_once()
    call = router.command_processor.handle_summarize_all_command.call_args
    assert call.args[1] == "/summarize_all@mybot"
    assert call.args[2:] == (20, "cid-20", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_unread_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/unread", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unread@mybot 10",
        uid=21,
        correlation_id="cid-21",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_unread_command.assert_awaited_once()
    call = router.command_processor.handle_unread_command.call_args
    assert call.args[1] == "/unread@mybot 10"
    assert call.args[2:] == (21, "cid-21", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_read_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/read", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/read@mybot 10",
        uid=22,
        correlation_id="cid-22",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_read_command.assert_awaited_once()
    call = router.command_processor.handle_read_command.call_args
    assert call.args[1] == "/read@mybot 10"
    assert call.args[2:] == (22, "cid-22", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_sync_karakeep_with_bot_mention_and_preserves_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/sync_karakeep", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/sync_karakeep@mybot",
        uid=29,
        correlation_id="cid-29",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_sync_karakeep_command.assert_awaited_once()
    call = router.command_processor.handle_sync_karakeep_command.call_args
    assert call.args[1] == "/sync_karakeep@mybot"
    assert call.args[2:] == (29, "cid-29", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_cdigest_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/cdigest", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/cdigest@mybot",
        uid=30,
        correlation_id="cid-30",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_cdigest_command.assert_awaited_once()
    call = router.command_processor.handle_cdigest_command.call_args
    assert call.args[1] == "/cdigest@mybot"
    assert call.args[2:] == (30, "cid-30", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_digest_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/digest", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/digest@mybot",
        uid=31,
        correlation_id="cid-31",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_digest_command.assert_awaited_once()
    call = router.command_processor.handle_digest_command.call_args
    assert call.args[1] == "/digest@mybot"
    assert call.args[2:] == (31, "cid-31", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_channels_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/channels", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/channels@mybot",
        uid=32,
        correlation_id="cid-32",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_channels_command.assert_awaited_once()
    call = router.command_processor.handle_channels_command.call_args
    assert call.args[1] == "/channels@mybot"
    assert call.args[2:] == (32, "cid-32", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_subscribe_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/subscribe", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/subscribe@mybot",
        uid=33,
        correlation_id="cid-33",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_subscribe_command.assert_awaited_once()
    call = router.command_processor.handle_subscribe_command.call_args
    assert call.args[1] == "/subscribe@mybot"
    assert call.args[2:] == (33, "cid-33", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_unsubscribe_with_bot_mention_and_preserves_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/unsubscribe", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unsubscribe@mybot",
        uid=34,
        correlation_id="cid-34",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_unsubscribe_command.assert_awaited_once()
    call = router.command_processor.handle_unsubscribe_command.call_args
    assert call.args[1] == "/unsubscribe@mybot"
    assert call.args[2:] == (34, "cid-34", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_init_session_with_bot_mention_and_preserves_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/init_session", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/init_session@mybot",
        uid=26,
        correlation_id="cid-26",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_init_session_command.assert_awaited_once()
    call = router.command_processor.handle_init_session_command.call_args
    assert call.args[1] == "/init_session@mybot"
    assert call.args[2:] == (26, "cid-26", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_settings_with_bot_mention_and_preserves_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/settings", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/settings@mybot",
        uid=27,
        correlation_id="cid-27",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_settings_command.assert_awaited_once()
    call = router.command_processor.handle_settings_command.call_args
    assert call.args[1] == "/settings@mybot"
    assert call.args[2:] == (27, "cid-27", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_routes_debug_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/debug", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/debug@mybot",
        uid=28,
        correlation_id="cid-28",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_debug_command.assert_awaited_once()
    call = router.command_processor.handle_debug_command.call_args
    assert call.args[1:] == (28, "cid-28", 0, 0.0)


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_command_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@mybot rust migration",
        uid=35,
        correlation_id="cid-35",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_command_with_mixed_case_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@MyBot rust migration",
        uid=38,
        correlation_id="cid-38",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd@MyBot rust migration",
        correlation_id="cid-38",
        actor_key="38",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@ rust migration",
        uid=39,
        correlation_id="cid-39",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd@ rust migration",
        correlation_id="cid-39",
        actor_key="39",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_mixed_case_command_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@mybot rust migration",
        uid=41,
        correlation_id="cid-41",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@mybot rust migration",
        correlation_id="cid-41",
        actor_key="41",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_mixed_case_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@MyBot rust migration",
        uid=42,
        correlation_id="cid-42",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@MyBot rust migration",
        correlation_id="cid-42",
        actor_key="42",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_mixed_case_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@ rust migration",
        uid=43,
        correlation_id="cid-43",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@ rust migration",
        correlation_id="cid-43",
        actor_key="43",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_command_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@mybot rust migration",
        uid=36,
        correlation_id="cid-36",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@mybot rust migration",
        correlation_id="cid-36",
        actor_key="36",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@MyBot rust migration",
        uid=37,
        correlation_id="cid-37",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@MyBot rust migration",
        correlation_id="cid-37",
        actor_key="37",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@ rust migration",
        uid=40,
        correlation_id="cid-40",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@ rust migration",
        correlation_id="cid-40",
        actor_key="40",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


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
