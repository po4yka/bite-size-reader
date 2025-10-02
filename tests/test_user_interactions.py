from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from app.adapters.telegram.message_router import MessageRouter
from app.adapters.telegram.url_handler import URLHandler
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database
from app.db.user_interactions import (
    async_safe_update_user_interaction,
    safe_update_user_interaction,
)


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
            fallback_models=tuple(),
            http_referer=None,
            x_title=None,
        ),
        runtime=RuntimeConfig(
            db_path=":memory:",
            log_level="INFO",
            request_timeout_sec=10,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "interactions.db"))
    db.migrate()
    return db


def test_message_router_logs_interaction(tmp_path) -> None:
    cfg = _make_config()
    db = _make_db(tmp_path)

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=Mock(),
        command_processor=Mock(),
        url_handler=cast(URLHandler, SimpleNamespace(url_processor=Mock())),
        forward_processor=Mock(),
        response_formatter=Mock(),
        audit_func=lambda *args, **kwargs: None,
    )

    interaction_id = router._log_user_interaction(  # noqa: SLF001
        user_id=42,
        chat_id=99,
        message_id=7,
        interaction_type="command",
        command="/start",
        input_text="hello",
        input_url=None,
        has_forward=True,
        forward_from_chat_id=555,
        forward_from_chat_title="Forwarded",
        forward_from_message_id=321,
        media_type="text",
        correlation_id="cid-123",
    )

    assert interaction_id > 0

    row = db.fetchone("SELECT * FROM user_interactions WHERE id = ?", (interaction_id,))
    assert row is not None
    assert row["user_id"] == 42
    assert row["interaction_type"] == "command"
    assert row["command"] == "/start"
    assert row["has_forward"] == 1
    assert row["structured_output_enabled"] == 1
    assert row["correlation_id"] == "cid-123"


def test_safe_update_user_interaction_updates_interaction(tmp_path) -> None:
    db = _make_db(tmp_path)

    interaction_id = db.insert_user_interaction(
        user_id=7,
        interaction_type="command",
        chat_id=11,
        message_id=22,
        command="/help",
        input_text="help",
        structured_output_enabled=True,
    )

    safe_update_user_interaction(
        db,
        interaction_id=interaction_id,
        response_sent=True,
        response_type="help",
        error_occurred=True,
        error_message="boom",
        processing_time_ms=1234,
        request_id=88,
    )

    row = db.fetchone(
        "SELECT response_sent, response_type, error_occurred, error_message, processing_time_ms, request_id "
        "FROM user_interactions WHERE id = ?",
        (interaction_id,),
    )

    assert row is not None
    assert row["response_sent"] == 1
    assert row["response_type"] == "help"
    assert row["error_occurred"] == 1
    assert row["error_message"] == "boom"
    assert row["processing_time_ms"] == 1234
    assert row["request_id"] == 88


def test_async_safe_update_user_interaction_updates_interaction(tmp_path) -> None:
    db = _make_db(tmp_path)

    interaction_id = db.insert_user_interaction(
        user_id=13,
        interaction_type="url",
        chat_id=44,
        message_id=55,
        command="/summary",
        input_text="go",
        structured_output_enabled=False,
    )

    asyncio.run(
        async_safe_update_user_interaction(
            db,
            interaction_id=interaction_id,
            response_sent=True,
            response_type="summary",
            error_occurred=False,
            error_message=None,
            request_id=99,
        )
    )

    row = db.fetchone(
        "SELECT response_sent, response_type, error_occurred, error_message, request_id "
        "FROM user_interactions WHERE id = ?",
        (interaction_id,),
    )

    assert row is not None
    assert row["response_sent"] == 1
    assert row["response_type"] == "summary"
    assert row["error_occurred"] == 0
    assert row["error_message"] is None
    assert row["request_id"] == 99
