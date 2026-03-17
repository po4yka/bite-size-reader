from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.content_extractor import ContentExtractionResult
from app.adapters.content.url_flow_context_builder import URLFlowContextBuilder
from app.adapters.content.url_flow_models import URLFlowRequest

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter


def _make_builder(*, long_context_model: str | None = None) -> tuple[URLFlowContextBuilder, Any]:
    cfg = SimpleNamespace(
        runtime=SimpleNamespace(preferred_lang="auto"),
        openrouter=SimpleNamespace(
            long_context_model=long_context_model,
            structured_output_mode="json",
        ),
    )
    content_extractor = MagicMock()
    content_extractor.extract_and_process_content = AsyncMock(
        return_value=ContentExtractionResult(
            request_id=1,
            content_text="Example content",
            content_source="firecrawl",
            detected_lang="en",
            title="Example Title",
            images=["img"],
        )
    )
    content_chunker = MagicMock()
    content_chunker.should_chunk_content = MagicMock(return_value=(True, 1000, ["chunk-1"]))
    response_formatter = SimpleNamespace(
        send_language_detection_notification=AsyncMock(),
        send_content_analysis_notification=AsyncMock(),
    )
    return (
        URLFlowContextBuilder(
            cfg=cfg,
            content_extractor=content_extractor,
            content_chunker=content_chunker,
            response_formatter=cast("ResponseFormatter", response_formatter),
        ),
        response_formatter,
    )


@pytest.mark.asyncio
async def test_builder_maps_extraction_to_context() -> None:
    builder, formatter = _make_builder(long_context_model=None)

    with patch(
        "app.adapters.content.url_flow_context_builder.get_url_system_prompt",
        return_value="prompt",
    ):
        context = await builder.build(
            URLFlowRequest(
                message=SimpleNamespace(),
                url_text="https://example.com",
                correlation_id="cid",
                interaction_id=1,
            )
        )

    assert context.req_id == 1
    assert context.chosen_lang == "en"
    assert context.system_prompt == "prompt"
    formatter.send_language_detection_notification.assert_awaited_once()
    formatter.send_content_analysis_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_mode_suppresses_language_notification() -> None:
    builder, formatter = _make_builder(long_context_model=None)

    with patch(
        "app.adapters.content.url_flow_context_builder.get_url_system_prompt",
        return_value="prompt",
    ):
        await builder.build(
            URLFlowRequest(
                message=SimpleNamespace(),
                url_text="https://example.com",
                batch_mode=True,
            )
        )

    formatter.send_language_detection_notification.assert_not_called()
    formatter.send_content_analysis_notification.assert_not_called()


@pytest.mark.asyncio
async def test_long_context_model_bypasses_chunking() -> None:
    builder, formatter = _make_builder(long_context_model="long-model")

    with patch(
        "app.adapters.content.url_flow_context_builder.get_url_system_prompt",
        return_value="prompt",
    ):
        context = await builder.build(
            URLFlowRequest(
                message=SimpleNamespace(),
                url_text="https://example.com",
            )
        )

    assert context.should_chunk is False
    assert context.chunks is None
    formatter.send_content_analysis_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_phase_change_receives_extracting_before_extraction() -> None:
    builder, _formatter = _make_builder(long_context_model=None)
    phase_change = AsyncMock()

    with patch(
        "app.adapters.content.url_flow_context_builder.get_url_system_prompt",
        return_value="prompt",
    ):
        await builder.build(
            URLFlowRequest(
                message=SimpleNamespace(),
                url_text="https://example.com",
                on_phase_change=phase_change,
            )
        )

    phase_change.assert_awaited_once_with("extracting", None, None, None)
