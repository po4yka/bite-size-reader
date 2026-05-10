"""Coverage for ForwardContentProcessor persistence (telegram_messages row)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.db.models import TelegramMessage
from tests.conftest import make_test_app_config

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


class _ForwardMessage:
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
        self.caption: str | None = None
        self.entities: list[Any] = []
        self.caption_entities: list[Any] = []
        self.forward_from_chat = _FwdChat(-100777, "Forwarded Channel")
        self.forward_from_message_id = 456
        self.forward_date = 1_700_000_100


async def test_process_forward_content_persists_snapshot(
    database: Database, session: AsyncSession
) -> None:
    cfg = make_test_app_config(db_path="/tmp/forward-persist.db", allowed_user_ids=(1,))

    formatter = MagicMock(spec=ResponseFormatter)
    formatter.send_forward_accepted_notification = AsyncMock()
    formatter.send_forward_language_notification = AsyncMock()

    processor = ForwardContentProcessor(
        cfg=cfg,
        db=database,
        response_formatter=formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )

    message = _ForwardMessage()

    req_id, _prompt, _lang, _system_prompt = await processor.process_forward_content(
        message, correlation_id="cid"
    )

    row = await session.scalar(select(TelegramMessage).where(TelegramMessage.request_id == req_id))
    assert row is not None
    assert row.forward_from_chat_id == message.forward_from_chat.id
    assert row.forward_from_chat_type == "channel"
    assert row.forward_from_chat_title == message.forward_from_chat.title
    assert row.forward_from_message_id == message.forward_from_message_id
    assert row.forward_date_ts == message.forward_date
    assert row.message_id == message.id
    assert row.chat_id == message.chat.id
    assert row.text_full == message.text
