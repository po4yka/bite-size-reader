"""Persistence-side coverage of media/forward fields on telegram_messages.

The legacy version of this file constructed a full TelegramBot just to
exercise its `_persist_message_snapshot`, which is a literal one-liner
that delegates to MessagePersistence. The async port drops that
indirection: the behaviour under test is the same (the right media_type
and file_ids land on the telegram_messages row), but the test runs
without spinning up the bot graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import TelegramMessage
from app.infrastructure.persistence.message_persistence import MessagePersistence
from tests.db_helpers_async import create_request

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


class _Ent:
    def __init__(self, t: str) -> None:
        self.type = t

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type}


class _Obj:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class _Chat:
    id = 1


class _MsgBase:
    def __init__(self) -> None:
        self.chat = _Chat()
        self.id = 10
        self.message_id = 10
        self.date = 1710000000
        self.text: str | None = None
        self.caption: str | None = None
        self.entities: tuple[_Ent, ...] | list[_Ent] = (_Ent("bold"),)
        self.caption_entities: tuple[_Ent, ...] | list[_Ent] = ()

    def to_dict(self) -> dict[str, int]:
        return {"id": self.id, "message_id": self.message_id}


async def _new_request(session: AsyncSession) -> int:
    return await create_request(
        session,
        type_="forward",
        status="pending",
        correlation_id=None,
        chat_id=1,
        user_id=1,
        route_version=1,
    )


async def _persist(
    database: Database, session: AsyncSession, message: object
) -> int:
    """Create a request, persist a message snapshot, return the request id."""
    req_id = await _new_request(session)
    await session.commit()
    persistence = MessagePersistence(db=database)
    await persistence.persist_message_snapshot(req_id, message)
    return req_id


async def _assert_media(
    session: AsyncSession,
    req_id: int,
    expected_type: str,
    expected_ids: list[str],
) -> None:
    row = await session.scalar(
        select(TelegramMessage).where(TelegramMessage.request_id == req_id)
    )
    assert row is not None
    assert row.media_type == expected_type
    if expected_ids:
        assert row.media_file_ids_json == expected_ids
    else:
        assert row.media_file_ids_json is None


async def test_photo_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.photo = _Obj("ph_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "photo", ["ph_1"])


async def test_video_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.video = _Obj("vid_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "video", ["vid_1"])


async def test_document_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.document = _Obj("doc_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "document", ["doc_1"])


async def test_audio_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.audio = _Obj("aud_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "audio", ["aud_1"])


async def test_voice_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.voice = _Obj("voc_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "voice", ["voc_1"])


async def test_animation_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.animation = _Obj("ani_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "animation", ["ani_1"])


async def test_sticker_snapshot(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.sticker = _Obj("stk_1")

    req_id = await _persist(database, session, Msg())
    await _assert_media(session, req_id, "sticker", ["stk_1"])


async def test_entities_merge(database: Database, session: AsyncSession) -> None:
    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.text = "Hello"
            self.caption = "World"
            self.entities = (_Ent("bold"),)
            self.caption_entities = (_Ent("url"),)

    req_id = await _persist(database, session, Msg())
    row = await session.scalar(
        select(TelegramMessage).where(TelegramMessage.request_id == req_id)
    )
    assert row is not None
    types = {e.get("type") for e in (row.entities_json or [])}  # type: ignore[union-attr]
    assert types == {"bold", "url"}


async def test_forward_snapshot(database: Database, session: AsyncSession) -> None:
    class _FwdChat:
        def __init__(self) -> None:
            self.id = 777
            self.type = "channel"
            self.title = "My Channel"

    class Msg(_MsgBase):
        def __init__(self) -> None:
            super().__init__()
            self.forward_from_chat = _FwdChat()
            self.forward_from_message_id = 555
            self.forward_date = 1700000000

    req_id = await _persist(database, session, Msg())
    row = await session.scalar(
        select(TelegramMessage).where(TelegramMessage.request_id == req_id)
    )
    assert row is not None
    assert row.forward_from_chat_id == 777
    assert row.forward_from_chat_type == "channel"
    assert row.forward_from_chat_title == "My Channel"
    assert row.forward_from_message_id == 555
    assert row.forward_date_ts == 1700000000
