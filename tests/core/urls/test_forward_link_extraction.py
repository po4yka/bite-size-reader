"""Tests for embedded-link extraction from forwarded posts."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.urls.forward_link_extraction import extract_forward_urls


def _entity(type_: str, url: str | None = None) -> SimpleNamespace:
    """Mimic the aiogram-shaped entity exposed by TelethonMessageAdapter.entities."""
    return SimpleNamespace(type=type_, url=url, offset=0, length=0)


def test_plain_text_url_extracted() -> None:
    msg = SimpleNamespace(entities=[])
    assert extract_forward_urls(msg, "read https://example.com/a now") == ["https://example.com/a"]


def test_text_link_entity_url_extracted() -> None:
    # Hyperlinked word -- the URL lives in entity.url, not the visible text.
    msg = SimpleNamespace(entities=[_entity("text_link", "https://wsj.com/grades")])
    assert extract_forward_urls(msg, "Выводы приводит The Wall Street Journal") == [
        "https://wsj.com/grades"
    ]


def test_mixed_sources_deduped_order_preserved() -> None:
    msg = SimpleNamespace(entities=[_entity("text_link", "https://b.com/x")])
    assert extract_forward_urls(msg, "see https://a.com/1 and more") == [
        "https://a.com/1",
        "https://b.com/x",
    ]


def test_duplicate_url_across_sources_deduped() -> None:
    msg = SimpleNamespace(entities=[_entity("text_link", "https://a.com/1")])
    assert extract_forward_urls(msg, "https://a.com/1") == ["https://a.com/1"]


def test_non_text_link_entities_ignored() -> None:
    msg = SimpleNamespace(entities=[_entity("bold"), _entity("mention")])
    assert extract_forward_urls(msg, "plain text, no links here") == []


def test_no_urls_returns_empty() -> None:
    assert extract_forward_urls(SimpleNamespace(entities=[]), "just text") == []


def test_missing_entities_attr_does_not_raise() -> None:
    assert extract_forward_urls(SimpleNamespace(), "https://a.com/1") == ["https://a.com/1"]


def test_none_message_does_not_raise() -> None:
    assert extract_forward_urls(None, "https://a.com/1") == ["https://a.com/1"]
