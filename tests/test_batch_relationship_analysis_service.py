from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.adapter_models.batch_analysis import RelationshipType
from app.adapter_models.batch_processing import URLBatchStatus
from app.adapters.telegram.batch_relationship_analysis_service import (
    BatchRelationshipAnalysisService,
)


def _make_batch_result() -> Any:
    urls = ["https://example.com/a", "https://example.com/b"]
    batch_status = URLBatchStatus.from_urls(urls)
    batch_status.mark_complete(urls[0], title="A", processing_time_ms=10)
    batch_status.mark_complete(urls[1], title="B", processing_time_ms=10)
    return SimpleNamespace(
        batch_status=batch_status,
        url_to_request_id={urls[0]: 1, urls[1]: 2},
        correlation_id="cid",
        uid=7,
    )


def _make_service() -> BatchRelationshipAnalysisService:
    summary_repo = SimpleNamespace(
        async_get_summaries_by_request_ids=AsyncMock(
            return_value={
                1: {"json_payload": {"title": "One", "summary_250": "A"}, "lang": "en"},
                2: {"json_payload": {"title": "Two", "summary_250": "B"}, "lang": "en"},
            }
        )
    )
    batch_session_repo = SimpleNamespace(
        async_create_batch_session=AsyncMock(return_value=91),
        async_add_batch_session_item=AsyncMock(),
        async_update_batch_session_counts=AsyncMock(),
        async_update_batch_session_status=AsyncMock(),
        async_update_batch_session_relationship=AsyncMock(),
        async_update_batch_session_combined_summary=AsyncMock(),
        async_get_batch_session_items=AsyncMock(return_value=[]),
        async_update_batch_session_item_series_info=AsyncMock(),
    )
    response_formatter = SimpleNamespace(safe_reply=AsyncMock())
    batch_config = SimpleNamespace(
        min_articles=2,
        use_llm_for_analysis=False,
        series_threshold=0.9,
        cluster_threshold=0.75,
        combined_summary_enabled=True,
    )
    return BatchRelationshipAnalysisService(
        summary_repo=summary_repo,
        batch_session_repo=batch_session_repo,
        llm_client=SimpleNamespace(),
        batch_config=cast("Any", batch_config),
        response_formatter=response_formatter,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_insufficient_article_count_skips_analysis() -> None:
    service = _make_service()
    batch_status = URLBatchStatus.from_urls(["https://example.com/only"])
    batch_status.mark_complete("https://example.com/only", title="One", processing_time_ms=10)
    batch_result = SimpleNamespace(
        batch_status=batch_status,
        url_to_request_id={"https://example.com/only": 1},
        correlation_id="cid",
        uid=1,
    )
    service._batch_config.min_articles = 2

    await service.analyze_batch(batch_result=batch_result, message=SimpleNamespace())

    service._batch_session_repo.async_create_batch_session.assert_not_called()
    service._response_formatter.safe_reply.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_unrelated_batch_completes_without_sending_message() -> None:
    service = _make_service()
    batch_result = _make_batch_result()
    cast("Any", service)._run_relationship_analysis = AsyncMock(
        return_value=SimpleNamespace(
            relationship_type=RelationshipType.UNRELATED,
            confidence=0.55,
            series_info=None,
            cluster_info=None,
            reasoning="No relationship",
            signals_used=[],
        )
    )

    await service.analyze_batch(batch_result=batch_result, message=SimpleNamespace())

    service._batch_session_repo.async_update_batch_session_relationship.assert_awaited_once()
    service._response_formatter.safe_reply.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_related_batch_persists_combined_summary_and_sends_result() -> None:
    service = _make_service()
    batch_result = _make_batch_result()
    cast("Any", service)._run_relationship_analysis = AsyncMock(
        return_value=SimpleNamespace(
            relationship_type=RelationshipType.DOMAIN_RELATED,
            confidence=0.81,
            series_info=None,
            cluster_info=None,
            reasoning="Shared publisher",
            signals_used=["domain"],
        )
    )
    cast("Any", service)._maybe_generate_combined_summary = AsyncMock(
        return_value=SimpleNamespace(
            model_dump=lambda: {"thematic_arc": "Arc"},
            thematic_arc="Arc",
            synthesized_insights=["Insight"],
            contradictions=[],
            reading_order_rationale=None,
            total_reading_time_min=None,
        )
    )

    await service.analyze_batch(batch_result=batch_result, message=SimpleNamespace())

    service._batch_session_repo.async_update_batch_session_combined_summary.assert_awaited_once()
    service._response_formatter.safe_reply.assert_awaited_once()  # type: ignore[attr-defined]
