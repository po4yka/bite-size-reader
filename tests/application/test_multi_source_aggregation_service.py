from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base_agent import AgentResult
from app.application.dto.aggregation import (
    MultiSourceAggregationOutput,
    MultiSourceExtractionOutput,
    SourceCoverageEntry,
    SourceExtractionItemResult,
)
from app.application.services.multi_source_aggregation_service import (
    MultiSourceAggregationService,
)
from app.domain.models.source import SourceKind


@pytest.mark.asyncio
async def test_multi_source_aggregation_service_records_synthesis_metrics() -> None:
    extraction_output = MultiSourceExtractionOutput(
        session_id=10,
        correlation_id="cid-service",
        status="completed",
        successful_count=2,
        failed_count=0,
        duplicate_count=0,
        items=[
            SourceExtractionItemResult(
                position=0,
                item_id=101,
                source_item_id="src_a",
                source_kind=SourceKind.WEB_ARTICLE,
                status="extracted",
            ),
            SourceExtractionItemResult(
                position=1,
                item_id=102,
                source_item_id="src_b",
                source_kind=SourceKind.X_POST,
                status="extracted",
            ),
        ],
    )
    aggregation_output = MultiSourceAggregationOutput(
        session_id=10,
        correlation_id="cid-service",
        status="completed",
        source_type="mixed",
        total_items=2,
        extracted_items=2,
        used_source_count=2,
        overview="Bundle synthesis",
        source_coverage=[
            SourceCoverageEntry(
                position=0,
                item_id=101,
                source_item_id="src_a",
                source_kind=SourceKind.WEB_ARTICLE,
                status="extracted",
                used_in_summary=True,
            ),
            SourceCoverageEntry(
                position=1,
                item_id=102,
                source_item_id="src_b",
                source_kind=SourceKind.X_POST,
                status="extracted",
                used_in_summary=True,
            ),
        ],
    )

    service = MultiSourceAggregationService(
        content_extractor=cast("Any", SimpleNamespace()),
        aggregation_session_repo=cast("Any", SimpleNamespace()),
        llm_client=None,
    )

    with (
        patch(
            "app.application.services.multi_source_aggregation_service.MultiSourceExtractionAgent.execute",
            new=AsyncMock(return_value=AgentResult.success_result(extraction_output)),
        ),
        patch(
            "app.application.services.multi_source_aggregation_service.MultiSourceAggregationAgent.execute",
            new=AsyncMock(
                return_value=AgentResult.success_result(
                    aggregation_output,
                    llm_cost_usd=0.023,
                )
            ),
        ),
        patch(
            "app.application.services.multi_source_aggregation_service.record_aggregation_synthesis"
        ) as metrics_mock,
    ):
        result = await service.aggregate(
            correlation_id="cid-service",
            user_id=1,
            submissions=[],
        )

    assert result.aggregation == aggregation_output
    metrics_mock.assert_called_once_with(
        source_type="mixed",
        bundle_profile="text_only",
        status="completed",
        used_source_count=2,
        coverage_ratio=1.0,
        cost_usd=0.023,
    )
