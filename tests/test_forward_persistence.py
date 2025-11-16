import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.config import (
    AppConfig,
    FirecrawlConfig,
    OpenRouterConfig,
    RuntimeConfig,
    TelegramConfig,
    YouTubeConfig,
)
from app.db.database import Database


class _ForwardMessage:
    """Simple forward message stub for persistence tests."""

    def __init__(self) -> None:
        class _Chat:
            def __init__(self, cid: int) -> None:
                self.id = cid

        class _User:
            def __init__(self, uid: int) -> None:
                self.id = uid

        class _FwdChat:
            def __init__(self, cid: int, title: str) -> None:
                self.id = cid
                self.type = "channel"
                self.title = title

        self.chat = _Chat(99)
        self.from_user = _User(7)
        self.id = 321
        self.message_id = 321
        self.text = "Forwarded post body"
        self.caption = None
        self.entities: list[Any] = []
        self.caption_entities: list[Any] = []
        self.forward_from_chat = _FwdChat(-100777, "Forwarded Channel")
        self.forward_from_message_id = 456
        self.forward_date = 1_700_000_100


class TestForwardMessagePersistence(unittest.IsolatedAsyncioTestCase):
    async def test_process_forward_content_persists_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "app.db")
            db = Database(db_path)
            db.migrate()

            cfg = AppConfig(
                telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=(1,)),
                firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
                openrouter=OpenRouterConfig(
                    api_key="or-dummy-key",
                    model="openai/gpt-4o-mini",
                    fallback_models=(),
                    http_referer=None,
                    x_title=None,
                    max_tokens=1024,
                    top_p=1.0,
                    temperature=0.2,
                ),
                youtube=YouTubeConfig(),
                runtime=RuntimeConfig(
                    db_path=db_path,
                    log_level="INFO",
                    request_timeout_sec=5,
                    preferred_lang="en",
                    debug_payloads=False,
                ),
            )

            formatter = MagicMock(spec=ResponseFormatter)
            formatter.send_forward_accepted_notification = AsyncMock()
            formatter.send_forward_language_notification = AsyncMock()

            processor = ForwardContentProcessor(
                cfg=cfg,
                db=db,
                response_formatter=formatter,
                audit_func=lambda *args, **kwargs: None,
            )

            message = _ForwardMessage()

            req_id, _prompt, _lang, _system_prompt = await processor.process_forward_content(
                message, correlation_id="cid"
            )

            row = db.fetchone(
                "SELECT forward_from_chat_id, forward_from_chat_type, forward_from_chat_title, "
                "forward_from_message_id, forward_date_ts, message_id, chat_id, text_full "
                "FROM telegram_messages WHERE request_id = ?",
                (req_id,),
            )

            assert row is not None
            assert row["forward_from_chat_id"] == message.forward_from_chat.id
            assert row["forward_from_chat_type"] == "channel"
            assert row["forward_from_chat_title"] == message.forward_from_chat.title
            assert row["forward_from_message_id"] == message.forward_from_message_id
            assert row["forward_date_ts"] == message.forward_date
            assert row["message_id"] == message.id
            assert row["chat_id"] == message.chat.id
            assert row["text_full"] == message.text
