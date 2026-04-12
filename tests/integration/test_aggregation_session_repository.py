"""Integration tests for aggregation session repository persistence."""

from __future__ import annotations

import pytest

from app.application.dto.aggregation import AggregationFailure, NormalizedSourceDocument
from app.domain.models.request import RequestStatus
from app.domain.models.source import (
    AggregationItemStatus,
    AggregationSessionStatus,
    SourceItem,
    SourceKind,
)
from app.infrastructure.persistence.sqlite.repositories.aggregation_session_repository import (
    SqliteAggregationSessionRepositoryAdapter,
)
from tests.integration.helpers import temp_db


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aggregation_session_repository_persists_duplicates_and_item_results() -> None:
    with temp_db() as db:
        from app.db.models import Request, User

        user = User.create(
            telegram_user_id=123456789,
            username="aggregator",
            is_owner=True,
        )
        request = Request.create(
            type="url",
            status=RequestStatus.PENDING.value,
            correlation_id="agg-item-req",
            user_id=user.telegram_user_id,
            input_url="https://example.com/a",
            normalized_url="https://example.com/a",
            dedupe_hash="agg-req-hash",
        )

        repo = SqliteAggregationSessionRepositoryAdapter(db)
        session_id = await repo.async_create_aggregation_session(
            user_id=user.telegram_user_id,
            correlation_id="agg-session-1",
            total_items=3,
            bundle_metadata={"submitted_via": "test"},
        )

        first = SourceItem.create(
            kind=SourceKind.WEB_ARTICLE,
            original_value="https://example.com/a?utm_source=test",
        )
        second = SourceItem.create(
            kind=SourceKind.YOUTUBE_VIDEO,
            original_value="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            external_id="dQw4w9WgXcQ",
        )
        duplicate = SourceItem.create(
            kind=SourceKind.WEB_ARTICLE,
            original_value="https://example.com/a",
        )

        first_item_id = await repo.async_add_aggregation_session_item(session_id, first, 0)
        second_item_id = await repo.async_add_aggregation_session_item(session_id, second, 1)
        duplicate_item_id = await repo.async_add_aggregation_session_item(session_id, duplicate, 2)

        items = await repo.async_get_aggregation_session_items(session_id)
        assert [item["position"] for item in items] == [0, 1, 2]
        assert items[0]["status"] == AggregationItemStatus.PENDING.value
        assert items[2]["status"] == AggregationItemStatus.DUPLICATE.value
        assert items[2]["duplicate_of_item_id"] == first_item_id

        first_document = NormalizedSourceDocument.from_extracted_content(
            source_item=first,
            text="Article body",
            title="Example",
            detected_language="en",
            content_source="markdown",
            metadata={"source": "firecrawl"},
        )
        await repo.async_update_aggregation_session_item_result(
            first_item_id,
            status=AggregationItemStatus.EXTRACTED,
            request_id=request.id,
            normalized_document=first_document,
            extraction_metadata={"latency_ms": 42},
        )
        await repo.async_update_aggregation_session_item_result(
            second_item_id,
            status=AggregationItemStatus.FAILED,
            failure=AggregationFailure(
                code="extract_timeout",
                message="Video transcript timed out",
                retryable=True,
                details={"timeout_s": 30},
            ),
        )
        await repo.async_update_aggregation_session_counts(
            session_id,
            successful_count=1,
            failed_count=1,
            duplicate_count=1,
        )
        await repo.async_update_aggregation_session_output(
            session_id,
            {
                "source_type": "mixed",
                "overview": "Bundle synthesis output",
                "used_source_count": 1,
            },
        )
        await repo.async_update_aggregation_session_status(
            session_id,
            status=AggregationSessionStatus.PARTIAL,
            processing_time_ms=1234,
        )

        session = await repo.async_get_aggregation_session(session_id)
        assert session is not None
        assert session["duplicate_count"] == 1
        assert session["failed_count"] == 1
        assert session["status"] == AggregationSessionStatus.PARTIAL.value
        assert session["bundle_metadata_json"]["submitted_via"] == "test"
        assert session["aggregation_output_json"]["source_type"] == "mixed"

        updated_items = await repo.async_get_aggregation_session_items(session_id)
        assert updated_items[0]["request"] == request.id
        assert updated_items[0]["normalized_document_json"]["title"] == "Example"
        assert updated_items[1]["failure_code"] == "extract_timeout"
        assert updated_items[1]["failure_details_json"]["timeout_s"] == 30
        assert duplicate_item_id == updated_items[2]["id"]
