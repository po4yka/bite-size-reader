from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.multi_source_aggregation_handler import (
    MultiSourceAggregationHandler,
)
from app.application.dto.aggregation import (
    MultiSourceAggregationOutput,
    MultiSourceExtractionOutput,
    SourceCoverageEntry,
    SourceExtractionItemResult,
)
from app.application.services.multi_source_aggregation_service import (
    MultiSourceAggregationRunResult,
)
from app.domain.models.source import SourceKind


def _make_result() -> MultiSourceAggregationRunResult:
    return MultiSourceAggregationRunResult(
        extraction=MultiSourceExtractionOutput(
            session_id=501,
            correlation_id="cid-single",
            status="completed",
            successful_count=1,
            failed_count=0,
            duplicate_count=0,
            items=[
                SourceExtractionItemResult(
                    position=0,
                    item_id=9001,
                    source_item_id="src_single",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    request_id=7001,
                )
            ],
        ),
        aggregation=MultiSourceAggregationOutput(
            session_id=501,
            correlation_id="cid-single",
            status="completed",
            source_type="web_article",
            total_items=1,
            extracted_items=1,
            used_source_count=1,
            overview="Single-source bundle summary",
            source_coverage=[
                SourceCoverageEntry(
                    position=0,
                    item_id=9001,
                    source_item_id="src_single",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    used_in_summary=True,
                )
            ],
        ),
    )


@pytest.mark.asyncio
async def test_handle_command_accepts_single_url_submission() -> None:
    response_formatter = SimpleNamespace(
        safe_reply=AsyncMock(),
        safe_reply_with_id=AsyncMock(),
        send_error_notification=AsyncMock(),
        send_message_draft=AsyncMock(),
        edit_message=AsyncMock(),
        clear_message_draft=MagicMock(),
        is_draft_streaming_enabled=MagicMock(return_value=True),
    )
    workflow_service = SimpleNamespace(aggregate=AsyncMock(return_value=_make_result()))
    handler = MultiSourceAggregationHandler(
        response_formatter=response_formatter,
        workflow_service=cast("Any", workflow_service),
    )
    message = SimpleNamespace(chat=SimpleNamespace(id=123), photo=None, document=None)

    handled = await handler.handle_command(
        message=message,
        text="/aggregate https://example.com/article",
        uid=42,
        correlation_id="cid-single",
    )

    assert handled is True
    workflow_service.aggregate.assert_awaited_once()
    assert workflow_service.aggregate.await_args.kwargs["submissions"][0].url == (
        "https://example.com/article"
    )
    response_formatter.safe_reply.assert_awaited()
    response_formatter.send_error_notification.assert_not_awaited()
