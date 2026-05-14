"""Regression tests: TelethonMessageAdapter must surface typed message entities.

Telethon encodes an entity's kind as the *class name* (``MessageEntityTextUrl``,
``MessageEntityUrl``, ...), not a ``.type`` field. ``_telegram_obj_to_dict`` walked
``__dict__`` and produced entity dicts with no ``type`` key, so
``MessageEntity._validate_type`` defaulted every entity to ``MENTION`` and
``TelegramMessage.get_urls()`` always returned ``[]`` -- hyperlinked words in
forwarded posts were invisible. The adapter now translates raw Telethon entities
into the aiogram-style shape the rest of the bot speaks.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityTextUrl,
    MessageEntityUrl,
)

from app.adapter_models.telegram.telegram_enums import MessageEntityType
from app.adapter_models.telegram.telegram_message import TelegramMessage
from app.adapters.telegram.telethon_compat import TelethonMessageAdapter


def _adapter(message: Any) -> TelethonMessageAdapter:
    event = SimpleNamespace(message=message, sender=None)
    return TelethonMessageAdapter(event, cast("Any", SimpleNamespace()))


def _message(text: str, entities: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        chat_id=555,
        raw_text=text,
        sender=SimpleNamespace(id=111, first_name="Owner", username="owner", bot=False),
        entities=entities,
    )


def test_text_link_entity_is_translated_with_url() -> None:
    # "приводит" hyperlinked to WSJ -- the exact shape of the user's example.
    text = "Выводы приводит The Wall Street Journal."
    entities = [MessageEntityTextUrl(offset=7, length=8, url="https://wsj.com/article")]
    adapter = _adapter(_message(text, entities))

    translated = adapter.entities
    assert len(translated) == 1
    assert translated[0].type == "text_link"
    assert translated[0].url == "https://wsj.com/article"
    assert translated[0].offset == 7
    assert translated[0].length == 8


def test_plain_url_entity_is_translated() -> None:
    text = "see https://example.com/x for details"
    entities = [MessageEntityUrl(offset=4, length=23)]
    adapter = _adapter(_message(text, entities))

    translated = adapter.entities
    assert len(translated) == 1
    assert translated[0].type == "url"


def test_caption_entities_is_empty_for_telethon_messages() -> None:
    adapter = _adapter(_message("hi", []))
    assert adapter.caption_entities == []


def test_message_without_entities_yields_empty_list() -> None:
    adapter = _adapter(SimpleNamespace(id=2, chat_id=555, raw_text="plain", sender=None))
    assert adapter.entities == []


def test_unknown_entity_class_is_skipped_not_crashed() -> None:
    class _WeirdFutureEntity:  # not a known Telethon entity class
        offset = 0
        length = 1

    adapter = _adapter(
        _message("bold text here", [MessageEntityBold(offset=0, length=4), _WeirdFutureEntity()])
    )
    translated = adapter.entities
    # the bold entity maps; the unknown one is dropped without raising
    assert [e.type for e in translated] == ["bold"]


def test_telegram_message_parser_sees_typed_entities_and_get_urls_works() -> None:
    """End-to-end: TelegramMessage.from_telegram_message preserves entity types,
    so get_urls() returns the hyperlink target instead of [].
    """
    text = "Выводы приводит The Wall Street Journal про оценки в вузах."
    entities = [MessageEntityTextUrl(offset=7, length=8, url="https://wsj.com/grades")]
    parsed = TelegramMessage.from_telegram_message(_adapter(_message(text, entities)))

    assert len(parsed.entities) == 1
    assert parsed.entities[0].type is MessageEntityType.TEXT_LINK
    assert parsed.get_urls() == ["https://wsj.com/grades"]
