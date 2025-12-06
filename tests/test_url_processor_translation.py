from __future__ import annotations

import unittest
from typing import Any, cast

from app.adapters.content.url_processor import URLProcessor


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []


class StubFormatter:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str | None, str | None]] = []

    async def send_russian_translation(
        self, message: DummyMessage, translated_text: str, correlation_id: str | None = None
    ) -> None:
        self.messages.append(("translation", translated_text, correlation_id))

    async def safe_reply(self, message: DummyMessage, text: str) -> None:
        self.messages.append(("safe", text, None))
        message.replies.append(text)


class StubSummarizer:
    def __init__(self, translated_text: str | None) -> None:
        self.translated_text = translated_text
        self.calls: list[tuple[dict, int, str | None]] = []

    async def translate_summary_to_ru(
        self, summary: dict, req_id: int, correlation_id: str | None = None
    ) -> str | None:
        self.calls.append((summary, req_id, correlation_id))
        return self.translated_text


class TestURLProcessorTranslation(unittest.IsolatedAsyncioTestCase):
    async def test_translation_skipped_when_not_needed(self) -> None:
        processor = URLProcessor.__new__(URLProcessor)
        formatter = StubFormatter()
        summarizer = StubSummarizer("перевод")
        processor.response_formatter = cast("Any", formatter)
        processor.llm_summarizer = cast("Any", summarizer)

        await processor._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hi"},
            req_id=1,
            correlation_id="cid-1",
            needs_translation=False,
        )

        assert formatter.messages == []

    async def test_translation_sent_when_available(self) -> None:
        formatter = StubFormatter()
        summarizer = StubSummarizer("Готовый перевод")

        processor = URLProcessor.__new__(URLProcessor)
        processor.response_formatter = cast("Any", formatter)
        processor.llm_summarizer = cast("Any", summarizer)

        await processor._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hello"},
            req_id=7,
            correlation_id="cid-ru",
            needs_translation=True,
        )

        assert ("translation", "Готовый перевод", "cid-ru") in formatter.messages
        assert summarizer.calls == [({"summary_250": "hello"}, 7, "cid-ru")]

    async def test_translation_fallback_notice_on_none(self) -> None:
        formatter = StubFormatter()
        summarizer = StubSummarizer(None)

        processor = URLProcessor.__new__(URLProcessor)
        processor.response_formatter = cast("Any", formatter)
        processor.llm_summarizer = cast("Any", summarizer)

        await processor._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hello"},
            req_id=3,
            correlation_id="cid-fail",
            needs_translation=True,
        )

        # Expect a safe reply when translation fails
        assert any(msg[0] == "safe" for msg in formatter.messages)
