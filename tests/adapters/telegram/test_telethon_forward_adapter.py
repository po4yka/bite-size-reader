"""Regression tests: TelethonMessageAdapter must surface forward metadata.

The Telethon migration left ``TelethonMessageAdapter`` without the aiogram-style
``forward_*`` attributes the router and ``TelegramMessage`` parser depend on.
``__getattr__`` delegated those names to the raw Telethon ``Message`` (which only
exposes ``fwd_from``), so ``getattr(message, "forward_from_chat", None)`` always
returned ``None`` and *every* forwarded channel post was misclassified as plain
text and answered with the generic "Send a URL or forward a channel post."
fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from telethon.tl.types import PeerChannel, PeerUser

from app.adapter_models.telegram.telegram_message import TelegramMessage
from app.adapters.telegram.telethon_compat import TelethonMessageAdapter


def _adapter(message: Any) -> TelethonMessageAdapter:
    event = SimpleNamespace(message=message, sender=None)
    return TelethonMessageAdapter(event, cast("Any", SimpleNamespace()))


def _channel_forward_message() -> SimpleNamespace:
    fwd_date = datetime(2026, 5, 14, 11, 25, tzinfo=UTC)
    fwd_from = SimpleNamespace(
        date=fwd_date,
        from_id=PeerChannel(channel_id=1234567890),
        from_name=None,
        channel_post=4321,
        post_author="The Bell Tech",
        saved_from_msg_id=None,
    )
    forward = SimpleNamespace(
        chat=SimpleNamespace(
            title="The Bell Tech",
            username="thebell_io",
            broadcast=True,
            megagroup=False,
        ),
        sender=None,
    )
    return SimpleNamespace(
        id=99,
        chat_id=555,
        raw_text="ИИ «раздувает» оценки, но не гарантирует знаний",
        sender=SimpleNamespace(id=111, first_name="Owner", username="owner", bot=False),
        fwd_from=fwd_from,
        forward=forward,
    )


def test_channel_forward_exposes_aiogram_style_attributes() -> None:
    adapter = _adapter(_channel_forward_message())

    chat = adapter.forward_from_chat
    assert chat is not None
    assert chat.id == -1001234567890  # marked channel id (Telethon get_peer_id)
    assert chat.title == "The Bell Tech"
    assert chat.username == "thebell_io"
    assert adapter.forward_from_message_id == 4321
    assert adapter.forward_date == datetime(2026, 5, 14, 11, 25, tzinfo=UTC)
    assert adapter.forward_from is None  # channel post, not a user forward


def test_channel_forward_is_recognized_by_telegram_message_parser() -> None:
    """The end-to-end contract: TelegramMessage.is_forwarded must be True so the
    router dispatches to the forward handler instead of the text fallback.
    """
    parsed = TelegramMessage.from_telegram_message(_adapter(_channel_forward_message()))

    assert parsed.is_forwarded is True
    assert parsed.forward_from_chat is not None
    assert parsed.forward_from_chat.id == -1001234567890
    assert parsed.forward_from_message_id == 4321


def test_user_forward_exposes_forward_from_and_no_chat() -> None:
    fwd_from = SimpleNamespace(
        date=datetime(2026, 5, 14, 9, 0, tzinfo=UTC),
        from_id=PeerUser(user_id=42),
        from_name=None,
        channel_post=None,
        saved_from_msg_id=None,
    )
    forward = SimpleNamespace(
        chat=None,
        sender=SimpleNamespace(first_name="Alice", username="alice", bot=False),
    )
    message = SimpleNamespace(
        id=7,
        chat_id=555,
        raw_text="forwarded note",
        sender=None,
        fwd_from=fwd_from,
        forward=forward,
    )
    adapter = _adapter(message)

    assert adapter.forward_from_chat is None
    user = adapter.forward_from
    assert user is not None
    assert user.id == 42
    assert user.first_name == "Alice"
    assert adapter.forward_date == datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def test_hidden_sender_forward_exposes_sender_name_only() -> None:
    fwd_from = SimpleNamespace(
        date=datetime(2026, 5, 14, 9, 0, tzinfo=UTC),
        from_id=None,
        from_name="Hidden User",
        channel_post=None,
        saved_from_msg_id=None,
    )
    message = SimpleNamespace(
        id=8,
        chat_id=555,
        raw_text="anon forward",
        sender=None,
        fwd_from=fwd_from,
        forward=None,
    )
    adapter = _adapter(message)

    assert adapter.forward_from_chat is None
    assert adapter.forward_from is None
    assert adapter.forward_sender_name == "Hidden User"


def test_non_forwarded_message_has_no_forward_metadata() -> None:
    message = SimpleNamespace(
        id=10,
        chat_id=555,
        raw_text="just a normal message",
        sender=None,
    )
    adapter = _adapter(message)

    assert adapter.forward_from_chat is None
    assert adapter.forward_from is None
    assert adapter.forward_date is None
    assert adapter.forward_from_message_id is None
    assert adapter.forward_sender_name is None
    assert TelegramMessage.from_telegram_message(adapter).is_forwarded is False
