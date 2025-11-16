from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.telegram.message_router import MessageRouter
from app.config import (
    AppConfig,
    FirecrawlConfig,
    OpenRouterConfig,
    RuntimeConfig,
    TelegramConfig,
    YouTubeConfig,
)
from app.db.database import Database


def _make_config() -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(
            api_id=1,
            api_hash="hash",
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234",
            allowed_user_ids=(1,),
        ),
        firecrawl=FirecrawlConfig(api_key="firecrawl-key"),
        openrouter=OpenRouterConfig(
            api_key="openrouter-key",
            model="test-model",
            fallback_models=(),
            http_referer=None,
            x_title=None,
        ),
        youtube=YouTubeConfig(),
        runtime=RuntimeConfig(
            db_path=":memory:",
            log_level="INFO",
            request_timeout_sec=10,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "forward-routing.db"))
    db.migrate()
    return db


@pytest.mark.asyncio
async def test_forward_message_with_url_prefers_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    del tmp_path_factory
    del request
    cfg = _make_config()
    db = _make_db(tmp_path)

    access_controller: Any = SimpleNamespace(check_access=AsyncMock(return_value=True))

    command_processor = Mock()

    url_handler: Any = SimpleNamespace(
        url_processor=Mock(),
        is_awaiting_url=Mock(return_value=False),
        has_pending_multi_links=Mock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_multi_link_confirmation=AsyncMock(),
        add_pending_multi_links=Mock(),
        add_awaiting_user=Mock(),
    )

    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())

    response_formatter: Any = SimpleNamespace(safe_reply=AsyncMock())

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=access_controller,
        command_processor=command_processor,
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )

    message = SimpleNamespace(
        text="https://example.com/article",
        forward_from_chat=SimpleNamespace(id=-100200300, title="Forwarded Channel"),
        forward_from_message_id=123,
    )

    await router._route_message_content(
        message,
        text=message.text,
        uid=1,
        has_forward=True,
        correlation_id="cid-1",
        interaction_id=99,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_awaited_once_with(
        message, correlation_id="cid-1", interaction_id=99
    )
    url_handler.handle_direct_url.assert_not_awaited()
    url_handler.handle_awaited_url.assert_not_awaited()
