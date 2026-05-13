"""Tests for user and chat upsert behavior during message persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.db.models import Chat, User
from app.infrastructure.persistence.message_persistence import MessagePersistence
from tests.db_helpers_async import create_request

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


@dataclass
class _DummyChat:
    id: int
    type: str | None = None
    title: str | None = None
    username: str | None = None


@dataclass
class _DummyUser:
    id: int
    username: str | None = None


class _DummyMessage:
    """Minimal message stub exposing attributes used by MessagePersistence."""

    def __init__(
        self,
        *,
        chat: _DummyChat,
        user: _DummyUser,
        text: str = "hello",
        date: int = 1,
    ) -> None:
        self.chat = chat
        self.from_user = user
        self.text = text
        self.caption = None
        self.entities: list[dict[str, str]] = []
        self.caption_entities: list[dict[str, str]] = []
        self.id = 1
        self.message_id = 1
        self.date = date

    def to_dict(self) -> dict[str, int]:
        return {"id": self.id, "message_id": self.message_id}


@pytest.fixture
def persistence(database: Database) -> MessagePersistence:
    return MessagePersistence(db=database)


async def _create_request(session: AsyncSession) -> int:
    return await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id=None,
        chat_id=1,
        user_id=1,
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash=None,
        input_message_id=1,
        content_text="https://example.com",
        route_version=1,
    )


async def test_persist_message_snapshot_populates_user_and_chat(
    session: AsyncSession, persistence: MessagePersistence
) -> None:
    req_id = await _create_request(session)
    await session.commit()

    message = _DummyMessage(
        chat=_DummyChat(id=101, type="private", title="My Chat", username="chatuser"),
        user=_DummyUser(id=202, username="alice"),
    )

    await persistence.persist_message_snapshot(req_id, message)

    user = await session.scalar(select(User).where(User.telegram_user_id == 202))
    assert user is not None
    assert user.username == "alice"

    chat = await session.scalar(select(Chat).where(Chat.chat_id == 101))
    assert chat is not None
    assert chat.type == "private"
    assert chat.title == "My Chat"
    assert chat.username == "chatuser"


async def test_persist_message_snapshot_with_missing_chat_type(
    session: AsyncSession, persistence: MessagePersistence
) -> None:
    """Regression: raw Telethon events surface a chat object without `.type`,
    which previously triggered a NOT NULL violation on `chats.type`. The
    repository must coerce None to a placeholder so the row still lands.
    """
    req_id = await _create_request(session)
    await session.commit()

    message = _DummyMessage(
        chat=_DummyChat(id=505, type=None, title=None, username="po4yka"),
        user=_DummyUser(id=606, username="po4yka"),
    )

    await persistence.persist_message_snapshot(req_id, message)

    chat = await session.scalar(select(Chat).where(Chat.chat_id == 505))
    assert chat is not None
    assert chat.type == "unknown"
    assert chat.username == "po4yka"


async def test_chat_upsert_does_not_overwrite_known_type_with_none(
    session: AsyncSession, persistence: MessagePersistence
) -> None:
    """A second message with no `.type` must not blank out the type that an
    earlier message established for the same chat.
    """
    first_req = await _create_request(session)
    await session.commit()
    first_message = _DummyMessage(
        chat=_DummyChat(id=707, type="private", title="First", username="u"),
        user=_DummyUser(id=808, username="u"),
    )
    await persistence.persist_message_snapshot(first_req, first_message)

    second_req = await _create_request(session)
    await session.commit()
    second_message = _DummyMessage(
        chat=_DummyChat(id=707, type=None, title="Second", username="u"),
        user=_DummyUser(id=808, username="u"),
    )
    await persistence.persist_message_snapshot(second_req, second_message)

    chat = await session.scalar(select(Chat).where(Chat.chat_id == 707))
    assert chat is not None
    assert chat.type == "private"
    assert chat.title == "Second"


async def test_persist_message_snapshot_refreshes_user_and_chat(
    session: AsyncSession, persistence: MessagePersistence
) -> None:
    first_req = await _create_request(session)
    await session.commit()
    first_message = _DummyMessage(
        chat=_DummyChat(id=303, type="group", title="Old Title", username="old_chat"),
        user=_DummyUser(id=404, username="old_user"),
    )
    await persistence.persist_message_snapshot(first_req, first_message)

    second_req = await _create_request(session)
    await session.commit()
    second_message = _DummyMessage(
        chat=_DummyChat(id=303, type="supergroup", title="New Title", username="new_chat"),
        user=_DummyUser(id=404, username="new_user"),
    )
    await persistence.persist_message_snapshot(second_req, second_message)

    user = await session.scalar(select(User).where(User.telegram_user_id == 404))
    assert user is not None
    assert user.username == "new_user"

    chat = await session.scalar(select(Chat).where(Chat.chat_id == 303))
    assert chat is not None
    assert chat.type == "supergroup"
    assert chat.title == "New Title"
    assert chat.username == "new_chat"
