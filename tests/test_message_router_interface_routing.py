from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.message_router_content import MessageRouterContentMixin
from app.migration.interface_router import TelegramCommandDecision


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
        self.interface_router = MagicMock()
        self.response_formatter = MagicMock()
        self.user_repo = MagicMock()
        self._lang = "en"


@pytest.mark.asyncio
async def test_route_command_message_preserves_original_alias_for_handler_payload() -> None:
    router = _Router()
    router.interface_router.resolve_telegram_command = AsyncMock(
        return_value=TelegramCommandDecision(command="/find", handled=True)
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
