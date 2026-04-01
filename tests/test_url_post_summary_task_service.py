from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.adapters.content.url_post_summary_task_service import URLPostSummaryTaskService


def _make_service() -> tuple[URLPostSummaryTaskService, Any, list[str]]:
    formatter = SimpleNamespace(
        safe_reply=AsyncMock(),
        is_reader_mode=AsyncMock(return_value=False),
        send_russian_translation=AsyncMock(),
        send_additional_insights_message=AsyncMock(),
        send_custom_article=AsyncMock(),
        sender=SimpleNamespace(),
    )
    summary_repo = SimpleNamespace(async_update_summary_insights=AsyncMock())
    article_generator = SimpleNamespace(
        translate_summary_to_ru=AsyncMock(return_value="перевод"),
        generate_custom_article=AsyncMock(return_value="article"),
    )
    insights_generator = SimpleNamespace(
        generate_additional_insights=AsyncMock(
            return_value={"topic_overview": "overview", "new_facts": [{"fact": "one"}]}
        )
    )
    scheduled: list[str] = []

    def _schedule_task(
        _registry: Any,
        coro: Any,
        _correlation_id: str | None,
        label: str,
        **_kwargs: Any,
    ) -> None:
        scheduled.append(label)
        coro.close()

    summary_delivery = SimpleNamespace(
        schedule_task=_schedule_task,
        drain_tasks=AsyncMock(),
    )
    related_reads_service = SimpleNamespace(find_related=AsyncMock(return_value=["item"]))
    service = URLPostSummaryTaskService(
        response_formatter=formatter,
        summary_repo=summary_repo,
        article_generator=article_generator,  # type: ignore[arg-type]
        insights_generator=insights_generator,  # type: ignore[arg-type]
        summary_delivery=summary_delivery,  # type: ignore[arg-type]
        related_reads_service=related_reads_service,  # type: ignore[arg-type]
    )
    return service, formatter, scheduled


@pytest.mark.asyncio
async def test_schedule_tasks_registers_translation_insights_custom_article_and_related_reads() -> (
    None
):
    service, formatter, scheduled = _make_service()

    await service.schedule_tasks(
        SimpleNamespace(),
        "content",
        "en",
        1,
        "cid",
        {"key_ideas": ["idea"], "topic_tags": ["#tag"]},
        needs_ru_translation=True,
        silent=False,
        url_hash="hash",
    )

    assert scheduled == [
        "ru_translation",
        "additional_insights",
        "custom_article",
        "related_reads",
    ]
    assert formatter.safe_reply.await_count == 2


@pytest.mark.asyncio
async def test_reader_mode_suppresses_reader_facing_prompts_and_custom_article() -> None:
    service, formatter, scheduled = _make_service()
    formatter.is_reader_mode.return_value = True

    await service.schedule_tasks(
        SimpleNamespace(),
        "content",
        "en",
        1,
        "cid",
        {"key_ideas": ["idea"], "topic_tags": ["#tag"]},
        needs_ru_translation=False,
        silent=False,
        url_hash="hash",
    )

    assert scheduled == ["additional_insights", "related_reads"]
    formatter.safe_reply.assert_not_called()


@pytest.mark.asyncio
async def test_handle_additional_insights_persists_and_notifies() -> None:
    service, formatter, _scheduled = _make_service()

    await service._handle_additional_insights(
        SimpleNamespace(),
        content_text="content",
        chosen_lang="en",
        req_id=7,
        correlation_id="cid-7",
        summary={"summary_250": "ok"},
        silent=False,
        url_hash="hash",
    )

    formatter.send_additional_insights_message.assert_awaited_once()
    service._summary_repo.async_update_summary_insights.assert_awaited_once_with(  # type: ignore[attr-defined]
        7,
        {"topic_overview": "overview", "new_facts": [{"fact": "one"}]},
    )


@pytest.mark.asyncio
async def test_aclose_drains_background_tasks() -> None:
    service, _formatter, _scheduled = _make_service()

    await service.aclose(timeout=2.0)

    service._summary_delivery.drain_tasks.assert_awaited_once()  # type: ignore[attr-defined]
