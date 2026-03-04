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
async def test_route_command_message_preserves_original_bare_alias_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@mybot",
        uid=53,
        correlation_id="cid-53",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/findonline@mybot",
        correlation_id="cid-53",
        actor_key="53",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/findonline@mybot"
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
async def test_route_command_message_preserves_original_bare_alias_with_mixed_case_bot_username() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@MyBot",
        uid=54,
        correlation_id="cid-54",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/findonline@MyBot",
        correlation_id="cid-54",
        actor_key="54",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/findonline@MyBot"
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
async def test_route_command_message_preserves_original_bare_alias_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/findonline@",
        uid=55,
        correlation_id="cid-55",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/findonline@",
        correlation_id="cid-55",
        actor_key="55",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/findonline@"
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
async def test_route_command_message_preserves_canonical_find_with_mixed_case_bot_username() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@MyBot rust migration",
        uid=60,
        correlation_id="cid-60",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/find@MyBot ")
    assert call.kwargs["command"] == "/find"


@pytest.mark.asyncio
async def test_route_command_message_preserves_canonical_find_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@ rust migration",
        uid=59,
        correlation_id="cid-59",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1].startswith("/find@ ")
    assert call.kwargs["command"] == "/find"


@pytest.mark.asyncio
async def test_route_command_message_preserves_bare_canonical_find_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@mybot",
        uid=56,
        correlation_id="cid-56",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/find@mybot",
        correlation_id="cid-56",
        actor_key="56",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/find@mybot"
    assert call.kwargs["command"] == "/find"


@pytest.mark.asyncio
async def test_route_command_message_preserves_bare_canonical_find_with_mixed_case_bot_username() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@MyBot",
        uid=57,
        correlation_id="cid-57",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/find@MyBot",
        correlation_id="cid-57",
        actor_key="57",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/find@MyBot"
    assert call.kwargs["command"] == "/find"


@pytest.mark.asyncio
async def test_route_command_message_preserves_bare_canonical_find_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command="/find", handled=True)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/find@",
        uid=58,
        correlation_id="cid-58",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is True
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/find@",
        correlation_id="cid-58",
        actor_key="58",
    )
    router.command_processor.handle_find_online_command.assert_called_once()
    call = router.command_processor.handle_find_online_command.call_args
    assert call.args[1] == "/find@"
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
async def test_route_command_message_ignores_unknown_bare_command_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@mybot",
        uid=47,
        correlation_id="cid-47",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd@mybot",
        correlation_id="cid-47",
        actor_key="47",
    )
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
async def test_route_command_message_ignores_unknown_bare_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@MyBot",
        uid=49,
        correlation_id="cid-49",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd@MyBot",
        correlation_id="cid-49",
        actor_key="49",
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
async def test_route_command_message_ignores_unknown_bare_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd@",
        uid=51,
        correlation_id="cid-51",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd@",
        correlation_id="cid-51",
        actor_key="51",
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
async def test_route_command_message_ignores_unknown_mixed_case_bare_command_with_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@mybot",
        uid=48,
        correlation_id="cid-48",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@mybot",
        correlation_id="cid-48",
        actor_key="48",
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
async def test_route_command_message_ignores_unknown_mixed_case_bare_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@MyBot",
        uid=50,
        correlation_id="cid-50",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@MyBot",
        correlation_id="cid-50",
        actor_key="50",
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
async def test_route_command_message_ignores_unknown_mixed_case_bare_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd@",
        uid=52,
        correlation_id="cid-52",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd@",
        correlation_id="cid-52",
        actor_key="52",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_command_without_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd rust migration",
        uid=40,
        correlation_id="cid-40",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd rust migration",
        correlation_id="cid-40",
        actor_key="40",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_bare_command_without_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/unknowncmd",
        uid=45,
        correlation_id="cid-45",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/unknowncmd",
        correlation_id="cid-45",
        actor_key="45",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_mixed_case_command_without_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd rust migration",
        uid=44,
        correlation_id="cid-44",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd rust migration",
        correlation_id="cid-44",
        actor_key="44",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_unknown_mixed_case_bare_command_without_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Unknowncmd",
        uid=46,
        correlation_id="cid-46",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Unknowncmd",
        correlation_id="cid-46",
        actor_key="46",
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
async def test_route_command_message_ignores_mixed_case_known_command_without_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline rust migration",
        uid=70,
        correlation_id="cid-70",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline rust migration",
        correlation_id="cid-70",
        actor_key="70",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_command_like_text_without_leading_slash() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="findonline rust migration",
        uid=72,
        correlation_id="cid-72",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="findonline rust migration",
        correlation_id="cid-72",
        actor_key="72",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_command_like_text_with_leading_whitespace() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text=" /findonline rust migration",
        uid=71,
        correlation_id="cid-71",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text=" /findonline rust migration",
        correlation_id="cid-71",
        actor_key="71",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_only_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/",
        uid=73,
        correlation_id="cid-73",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/",
        correlation_id="cid-73",
        actor_key="73",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/ findonline rust",
        uid=74,
        correlation_id="cid-74",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/ findonline rust",
        correlation_id="cid-74",
        actor_key="74",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_tab_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\tfindonline rust",
        uid=75,
        correlation_id="cid-75",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\tfindonline rust",
        correlation_id="cid-75",
        actor_key="75",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_newline_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\nfindonline rust",
        uid=76,
        correlation_id="cid-76",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\nfindonline rust",
        correlation_id="cid-76",
        actor_key="76",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_carriage_return_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\rfindonline rust",
        uid=77,
        correlation_id="cid-77",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\rfindonline rust",
        correlation_id="cid-77",
        actor_key="77",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_form_feed_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\x0cfindonline rust",
        uid=78,
        correlation_id="cid-78",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\x0cfindonline rust",
        correlation_id="cid-78",
        actor_key="78",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_vertical_tab_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\x0bfindonline rust",
        uid=79,
        correlation_id="cid-79",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\x0bfindonline rust",
        correlation_id="cid-79",
        actor_key="79",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_non_breaking_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u00a0findonline rust",
        uid=80,
        correlation_id="cid-80",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u00a0findonline rust",
        correlation_id="cid-80",
        actor_key="80",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_narrow_no_break_space_command_like_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u202ffindonline rust",
        uid=81,
        correlation_id="cid-81",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u202ffindonline rust",
        correlation_id="cid-81",
        actor_key="81",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_figure_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2007findonline rust",
        uid=82,
        correlation_id="cid-82",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2007findonline rust",
        correlation_id="cid-82",
        actor_key="82",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_thin_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2009findonline rust",
        uid=84,
        correlation_id="cid-84",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2009findonline rust",
        correlation_id="cid-84",
        actor_key="84",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_ideographic_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u3000findonline rust",
        uid=83,
        correlation_id="cid-83",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u3000findonline rust",
        correlation_id="cid-83",
        actor_key="83",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_hair_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u200afindonline rust",
        uid=85,
        correlation_id="cid-85",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u200afindonline rust",
        correlation_id="cid-85",
        actor_key="85",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_medium_mathematical_space_command_like_text() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u205ffindonline rust",
        uid=86,
        correlation_id="cid-86",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u205ffindonline rust",
        correlation_id="cid-86",
        actor_key="86",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_punctuation_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2008findonline rust",
        uid=87,
        correlation_id="cid-87",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2008findonline rust",
        correlation_id="cid-87",
        actor_key="87",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_six_per_em_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2006findonline rust",
        uid=88,
        correlation_id="cid-88",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2006findonline rust",
        correlation_id="cid-88",
        actor_key="88",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_four_per_em_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2005findonline rust",
        uid=89,
        correlation_id="cid-89",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2005findonline rust",
        correlation_id="cid-89",
        actor_key="89",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_three_per_em_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2004findonline rust",
        uid=90,
        correlation_id="cid-90",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2004findonline rust",
        correlation_id="cid-90",
        actor_key="90",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_em_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2003findonline rust",
        uid=91,
        correlation_id="cid-91",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2003findonline rust",
        correlation_id="cid-91",
        actor_key="91",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_en_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2002findonline rust",
        uid=92,
        correlation_id="cid-92",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2002findonline rust",
        correlation_id="cid-92",
        actor_key="92",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_em_quad_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2001findonline rust",
        uid=93,
        correlation_id="cid-93",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2001findonline rust",
        correlation_id="cid-93",
        actor_key="93",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_en_quad_space_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2000findonline rust",
        uid=94,
        correlation_id="cid-94",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2000findonline rust",
        correlation_id="cid-94",
        actor_key="94",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_ogham_space_mark_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u1680findonline rust",
        uid=95,
        correlation_id="cid-95",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u1680findonline rust",
        correlation_id="cid-95",
        actor_key="95",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_line_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2028findonline rust",
        uid=96,
        correlation_id="cid-96",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2028findonline rust",
        correlation_id="cid-96",
        actor_key="96",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_paragraph_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u2029findonline rust",
        uid=97,
        correlation_id="cid-97",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u2029findonline rust",
        correlation_id="cid-97",
        actor_key="97",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_next_line_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0085findonline rust",
        uid=98,
        correlation_id="cid-98",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0085findonline rust",
        correlation_id="cid-98",
        actor_key="98",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_file_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u001cfindonline rust",
        uid=99,
        correlation_id="cid-99",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u001cfindonline rust",
        correlation_id="cid-99",
        actor_key="99",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_group_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u001dfindonline rust",
        uid=100,
        correlation_id="cid-100",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u001dfindonline rust",
        correlation_id="cid-100",
        actor_key="100",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_record_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u001efindonline rust",
        uid=101,
        correlation_id="cid-101",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u001efindonline rust",
        correlation_id="cid-101",
        actor_key="101",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_unit_separator_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u001ffindonline rust",
        uid=102,
        correlation_id="cid-102",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u001ffindonline rust",
        correlation_id="cid-102",
        actor_key="102",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_delete_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u007ffindonline rust",
        uid=103,
        correlation_id="cid-103",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u007ffindonline rust",
        correlation_id="cid-103",
        actor_key="103",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_padding_character_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0080findonline rust",
        uid=104,
        correlation_id="cid-104",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0080findonline rust",
        correlation_id="cid-104",
        actor_key="104",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_high_octet_preset_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0081findonline rust",
        uid=105,
        correlation_id="cid-105",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0081findonline rust",
        correlation_id="cid-105",
        actor_key="105",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_break_permitted_here_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0082findonline rust",
        uid=106,
        correlation_id="cid-106",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0082findonline rust",
        correlation_id="cid-106",
        actor_key="106",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_no_break_here_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0083findonline rust",
        uid=107,
        correlation_id="cid-107",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0083findonline rust",
        correlation_id="cid-107",
        actor_key="107",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_slash_index_command_like_text() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/\u0084findonline rust",
        uid=108,
        correlation_id="cid-108",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/\u0084findonline rust",
        correlation_id="cid-108",
        actor_key="108",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_canonical_command_without_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find rust migration",
        uid=67,
        correlation_id="cid-67",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find rust migration",
        correlation_id="cid-67",
        actor_key="67",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_canonical_command_without_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find",
        uid=68,
        correlation_id="cid-68",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find",
        correlation_id="cid-68",
        actor_key="68",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_canonical_command_with_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@mybot rust migration",
        uid=61,
        correlation_id="cid-61",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@mybot rust migration",
        correlation_id="cid-61",
        actor_key="61",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_canonical_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@ rust migration",
        uid=65,
        correlation_id="cid-65",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@ rust migration",
        correlation_id="cid-65",
        actor_key="65",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_canonical_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@",
        uid=66,
        correlation_id="cid-66",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@",
        correlation_id="cid-66",
        actor_key="66",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_canonical_command_with_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@mybot",
        uid=63,
        correlation_id="cid-63",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@mybot",
        correlation_id="cid-63",
        actor_key="63",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_canonical_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@MyBot rust migration",
        uid=62,
        correlation_id="cid-62",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@MyBot rust migration",
        correlation_id="cid-62",
        actor_key="62",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_canonical_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Find@MyBot",
        uid=64,
        correlation_id="cid-64",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Find@MyBot",
        correlation_id="cid-64",
        actor_key="64",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_command_with_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@mybot",
        uid=47,
        correlation_id="cid-47",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@mybot",
        correlation_id="cid-47",
        actor_key="47",
    )
    router.command_processor.handle_find_online_command.assert_not_awaited()
    router.command_processor.handle_find_local_command.assert_not_awaited()
    router.command_processor.handle_start_command.assert_not_awaited()
    router.command_processor.handle_debug_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_command_message_ignores_mixed_case_bare_command_without_bot_mention() -> None:
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline",
        uid=69,
        correlation_id="cid-69",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline",
        correlation_id="cid-69",
        actor_key="69",
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
async def test_route_command_message_ignores_mixed_case_bare_command_with_mixed_case_bot_mention() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@MyBot",
        uid=48,
        correlation_id="cid-48",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@MyBot",
        correlation_id="cid-48",
        actor_key="48",
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
async def test_route_command_message_ignores_mixed_case_bare_command_with_empty_bot_mention_suffix() -> (
    None
):
    router = _Router()
    router.telegram_runtime_runner.resolve_command_route = AsyncMock(
        return_value=TelegramRuntimeCommandDecision(command=None, handled=False)
    )

    handled = await router._route_command_message(
        message=SimpleNamespace(),
        text="/Findonline@",
        uid=49,
        correlation_id="cid-49",
        interaction_id=0,
        start_time=0.0,
    )

    assert handled is False
    router.telegram_runtime_runner.resolve_command_route.assert_awaited_once_with(
        text="/Findonline@",
        correlation_id="cid-49",
        actor_key="49",
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
