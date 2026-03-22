"""Tests for URLProcessor orchestration with batch-mode aware collaborators."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.adapters.content.summarization_models import InteractiveSummaryResult
from app.adapters.content.url_flow_models import (
    URLFlowContext,
    URLFlowRequest,
    URLProcessingFlowResult,
)
from app.adapters.content.url_processor import URLProcessor


class DummyChat:
    id = 123


class DummyMessage:
    def __init__(self) -> None:
        self.chat = DummyChat()


def _make_context(*, should_chunk: bool = False) -> URLFlowContext:
    return URLFlowContext(
        dedupe_hash="hash",
        req_id=1,
        content_text="Test content for the article.",
        title="Test Title",
        images=[],
        chosen_lang="en",
        needs_ru_translation=False,
        system_prompt="prompt",
        should_chunk=should_chunk,
        max_chars=10_000,
        chunks=["chunk-1", "chunk-2"] if should_chunk else None,
    )


def _make_processor(
    *,
    cached_result: URLProcessingFlowResult | None = None,
    context: URLFlowContext | None = None,
    summary_result: InteractiveSummaryResult | None = None,
    chunk_summary: dict[str, Any] | None = None,
) -> Any:
    proc: Any = URLProcessor.__new__(URLProcessor)
    cfg = MagicMock()
    cfg.openrouter.model = "test-model"
    proc.cfg = cfg
    proc.response_formatter = AsyncMock()
    proc.cached_summary_responder = MagicMock()
    proc.cached_summary_responder.maybe_reply = AsyncMock(return_value=cached_result)
    proc.context_builder = MagicMock()
    proc.context_builder.build = AsyncMock(return_value=context or _make_context())
    proc.content_chunker = MagicMock()
    proc.content_chunker.process_chunks = AsyncMock(
        return_value=chunk_summary or {"summary_250": "chunked", "tldr": "chunked"}
    )
    proc.semantic_helper = MagicMock()
    proc.semantic_helper.enrich_with_rag_fields = AsyncMock(
        side_effect=lambda payload, **_kwargs: payload
    )
    proc.interactive_summary_service = MagicMock()
    proc.interactive_summary_service.summarize = AsyncMock(
        return_value=summary_result
        or InteractiveSummaryResult(
            summary={"summary_250": "ok", "tldr": "ok"},
            llm_result=MagicMock(),
            served_from_cache=False,
            model_used="test-model",
        )
    )
    proc.summary_delivery = MagicMock()
    proc.summary_delivery.deliver_summary = AsyncMock(
        return_value=URLProcessingFlowResult.from_summary(
            {"summary_250": "ok", "tldr": "ok"},
            request_id=1,
        )
    )
    proc.summary_delivery.send_processing_failure = AsyncMock(
        return_value=URLProcessingFlowResult(success=False)
    )
    proc.post_summary_tasks = MagicMock()
    proc.post_summary_tasks.schedule_tasks = AsyncMock()
    proc.summarization_runtime = MagicMock()
    proc.summarization_runtime.semantic_helper = proc.semantic_helper
    return proc


class TestURLProcessorBatchMode(unittest.IsolatedAsyncioTestCase):
    async def test_batch_mode_skips_post_summary_tasks(self) -> None:
        proc = _make_processor()

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/article",
                correlation_id="cid-1",
                batch_mode=True,
            )
        )

        assert result.success
        proc.post_summary_tasks.schedule_tasks.assert_not_called()
        proc.summary_delivery.deliver_summary.assert_awaited_once()

    async def test_default_mode_schedules_post_summary_tasks(self) -> None:
        proc = _make_processor()

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/article",
                correlation_id="cid-2",
            )
        )

        assert result.success
        proc.post_summary_tasks.schedule_tasks.assert_awaited_once()

    async def test_cached_result_short_circuits_remaining_flow(self) -> None:
        cached = URLProcessingFlowResult.from_summary(
            {"summary_250": "cached", "tldr": "cached"},
            cached=True,
            request_id=10,
        )
        proc = _make_processor(cached_result=cached)

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/cached",
                correlation_id="cid-cache",
            )
        )

        assert result.cached is True
        proc.context_builder.build.assert_not_called()
        proc.interactive_summary_service.summarize.assert_not_called()
        proc.summary_delivery.deliver_summary.assert_not_called()

    async def test_summary_failure_routes_to_delivery_failure_handler(self) -> None:
        proc = _make_processor(
            summary_result=InteractiveSummaryResult(
                summary=None,
                llm_result=None,
                served_from_cache=False,
                model_used=None,
            )
        )

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/fail",
                correlation_id="cid-fail",
                batch_mode=True,
            )
        )

        assert result.success is False
        proc.summary_delivery.send_processing_failure.assert_awaited_once()
        proc.post_summary_tasks.schedule_tasks.assert_not_called()

    async def test_chunked_flow_uses_chunker_and_skips_interactive_service(self) -> None:
        proc = _make_processor(context=_make_context(should_chunk=True))

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/chunked",
                correlation_id="cid-chunk",
            )
        )

        assert result.success
        proc.content_chunker.process_chunks.assert_awaited_once()
        proc.semantic_helper.enrich_with_rag_fields.assert_awaited_once()
        proc.interactive_summary_service.summarize.assert_not_called()

    async def test_exception_sends_error_notification_only_when_not_batch(self) -> None:
        proc = _make_processor()
        proc.context_builder.build = AsyncMock(side_effect=RuntimeError("boom"))

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/error",
                correlation_id="cid-error",
            )
        )

        assert result.success is False
        proc.response_formatter.send_error_notification.assert_awaited_once()

    async def test_batch_mode_exception_suppresses_error_notification(self) -> None:
        proc = _make_processor()
        proc.context_builder.build = AsyncMock(side_effect=RuntimeError("boom"))

        result = await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/error",
                correlation_id="cid-error-batch",
                batch_mode=True,
            )
        )

        assert result.success is False
        proc.response_formatter.send_error_notification.assert_not_called()

    async def test_context_builder_receives_full_request_envelope(self) -> None:
        proc = _make_processor()

        await proc.handle_url_flow(
            URLFlowRequest(
                message=DummyMessage(),
                url_text="https://example.com/request",
                correlation_id="cid-request",
                interaction_id=9,
                silent=True,
                batch_mode=True,
                on_phase_change=AsyncMock(),
                progress_tracker=MagicMock(),
            )
        )

        request = proc.context_builder.build.await_args.args[0]
        assert isinstance(request, URLFlowRequest)
        assert request.correlation_id == "cid-request"
        assert request.interaction_id == 9
        assert request.silent is True
        assert request.batch_mode is True
