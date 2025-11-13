"""Tests for user and chat upsert behavior during message persistence."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.adapters.telegram.message_persistence import MessagePersistence
from app.db.database import Database


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
def db(tmp_path) -> Database:
    path = tmp_path / "app.db"
    database = Database(str(path))
    database.migrate()
    return database


@pytest.fixture
def persistence(db: Database) -> MessagePersistence:
    return MessagePersistence(db=db)


def _create_request(db: Database) -> int:
    return db.create_request(
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


def test_persist_message_snapshot_populates_user_and_chat(
    db: Database, persistence: MessagePersistence
) -> None:
    req_id = _create_request(db)
    message = _DummyMessage(
        chat=_DummyChat(id=101, type="private", title="My Chat", username="chatuser"),
        user=_DummyUser(id=202, username="alice"),
    )

    persistence.persist_message_snapshot(req_id, message)

    user_row = db.fetchone("SELECT username FROM users WHERE telegram_user_id = ?", (202,))
    assert user_row is not None
    assert user_row["username"] == "alice"

    chat_row = db.fetchone("SELECT type, title, username FROM chats WHERE chat_id = ?", (101,))
    assert chat_row is not None
    assert chat_row["type"] == "private"
    assert chat_row["title"] == "My Chat"
    assert chat_row["username"] == "chatuser"


def test_persist_message_snapshot_refreshes_user_and_chat(
    db: Database, persistence: MessagePersistence
) -> None:
    first_req = _create_request(db)
    first_message = _DummyMessage(
        chat=_DummyChat(id=303, type="group", title="Old Title", username="old_chat"),
        user=_DummyUser(id=404, username="old_user"),
    )
    persistence.persist_message_snapshot(first_req, first_message)

    second_req = _create_request(db)
    second_message = _DummyMessage(
        chat=_DummyChat(id=303, type="supergroup", title="New Title", username="new_chat"),
        user=_DummyUser(id=404, username="new_user"),
    )
    persistence.persist_message_snapshot(second_req, second_message)

    user_row = db.fetchone("SELECT username FROM users WHERE telegram_user_id = ?", (404,))
    assert user_row is not None
    assert user_row["username"] == "new_user"

    chat_row = db.fetchone("SELECT type, title, username FROM chats WHERE chat_id = ?", (303,))
    assert chat_row is not None
    assert chat_row["type"] == "supergroup"
    assert chat_row["title"] == "New Title"
    assert chat_row["username"] == "new_chat"
