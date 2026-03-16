from __future__ import annotations

import unittest
from typing import Any, cast

from app.adapters.content.url_post_summary_task_service import URLPostSummaryTaskService


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []


class StubFormatter:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str | None, str | None]] = []

    async def send_russian_translation(
        self,
        message: DummyMessage,
        translated_text: str,
        correlation_id: str | None = None,
    ) -> None:
        self.messages.append(("translation", translated_text, correlation_id))

    async def safe_reply(self, message: DummyMessage, text: str) -> None:
        self.messages.append(("safe", text, None))
        message.replies.append(text)


class StubArticleGenerator:
    def __init__(self, translated_text: str | None) -> None:
        self.translated_text = translated_text
        self.calls: list[tuple[dict[str, Any], int, str | None]] = []

    async def translate_summary_to_ru(
        self,
        summary: dict[str, Any],
        *,
        req_id: int,
        correlation_id: str | None = None,
        url_hash: str | None = None,
        source_lang: str | None = None,
    ) -> str | None:
        self.calls.append((summary, req_id, correlation_id))
        return self.translated_text


def _make_service(
    translated_text: str | None,
) -> tuple[URLPostSummaryTaskService, StubFormatter, StubArticleGenerator]:
    formatter = StubFormatter()
    article_generator = StubArticleGenerator(translated_text)
    service = URLPostSummaryTaskService(
        response_formatter=cast("Any", formatter),
        summary_repo=cast("Any", object()),
        article_generator=cast("Any", article_generator),
        insights_generator=cast("Any", object()),
        summary_delivery=cast("Any", object()),
        related_reads_service=None,
    )
    return service, formatter, article_generator


class TestURLProcessorTranslation(unittest.IsolatedAsyncioTestCase):
    async def test_translation_skipped_when_not_needed(self) -> None:
        service, formatter, _article_generator = _make_service("перевод")

        await service._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hi"},
            req_id=1,
            correlation_id="cid-1",
            needs_translation=False,
        )

        assert formatter.messages == []

    async def test_translation_sent_when_available(self) -> None:
        service, formatter, article_generator = _make_service("Готовый перевод")

        await service._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hello"},
            req_id=7,
            correlation_id="cid-ru",
            needs_translation=True,
        )

        assert ("translation", "Готовый перевод", "cid-ru") in formatter.messages
        assert article_generator.calls == [({"summary_250": "hello"}, 7, "cid-ru")]

    async def test_translation_fallback_notice_on_none(self) -> None:
        service, formatter, _article_generator = _make_service(None)

        await service._maybe_send_russian_translation(
            DummyMessage(),
            {"summary_250": "hello"},
            req_id=3,
            correlation_id="cid-fail",
            needs_translation=True,
        )

        assert any(msg[0] == "safe" for msg in formatter.messages)
