from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.multi_source_aggregation_agent import (
    MultiSourceAggregationAgent,
    MultiSourceAggregationInput,
)
from app.application.dto.aggregation import (
    AggregationEvidenceKind,
    AggregationRelationshipSignal,
    ExtractedTextKind,
    MultiSourceAggregationOutput,
    NormalizedSourceDocument,
    SourceExtractionItemResult,
)
from app.domain.models.source import AggregationItemStatus, SourceItem, SourceKind
from app.infrastructure.persistence.sqlite.repositories.aggregation_session_repository import (
    SqliteAggregationSessionRepositoryAdapter,
)
from tests.integration.helpers import temp_db


def _make_document(
    *,
    kind: SourceKind,
    original_value: str,
    text: str,
    title: str,
    text_kind: ExtractedTextKind = ExtractedTextKind.BODY,
    metadata: dict[str, object] | None = None,
) -> NormalizedSourceDocument:
    source_item = SourceItem.create(
        kind=kind,
        original_value=original_value,
        title_hint=title,
    )
    return NormalizedSourceDocument.from_extracted_content(
        source_item=source_item,
        text=text,
        title=title,
        detected_language="en",
        content_source="markdown",
        metadata=metadata,
        text_kind=text_kind,
    )


@pytest.mark.asyncio
async def test_multi_source_aggregation_agent_builds_fallback_synthesis_and_persists_output() -> (
    None
):
    with temp_db() as db:
        from app.db.models import User

        user = User.create(
            telegram_user_id=123456789,
            username="bundle-user",
            is_owner=True,
        )
        repo = SqliteAggregationSessionRepositoryAdapter(db)
        session_id = await repo.async_create_aggregation_session(
            user_id=user.telegram_user_id,
            correlation_id="agg-phase7-fallback",
            total_items=4,
        )

        document_one = _make_document(
            kind=SourceKind.WEB_ARTICLE,
            original_value="https://example.com/report",
            title="Quarterly report",
            text=(
                "The company launched a new device in Berlin on Tuesday. "
                "Revenue grew 20% in Q1 for Acme."
            ),
            metadata={"topic_tags": ["#earnings"], "entities": [{"name": "Berlin"}]},
        )
        document_two = _make_document(
            kind=SourceKind.X_POST,
            original_value="https://x.com/acme/status/123",
            title="Launch thread",
            text=(
                "The company launched a new device in Berlin on Tuesday. "
                "Revenue grew 12% in Q1 for Acme."
            ),
            metadata={"topic_tags": ["launch"], "entities": ["Acme"]},
        )
        duplicate_source = SourceItem.create(
            kind=SourceKind.WEB_ARTICLE,
            original_value="https://example.com/report?utm_source=test",
            title_hint="Quarterly report duplicate",
        )
        failed_source = SourceItem.create(
            kind=SourceKind.THREADS_POST,
            original_value="https://www.threads.net/@acme/post/abc",
            title_hint="Broken thread",
        )

        items = [
            SourceExtractionItemResult(
                position=0,
                item_id=101,
                source_item_id=document_one.source_item_id,
                source_kind=document_one.source_kind,
                status=AggregationItemStatus.EXTRACTED.value,
                normalized_document=document_one,
            ),
            SourceExtractionItemResult(
                position=1,
                item_id=102,
                source_item_id=document_two.source_item_id,
                source_kind=document_two.source_kind,
                status=AggregationItemStatus.EXTRACTED.value,
                normalized_document=document_two,
            ),
            SourceExtractionItemResult(
                position=2,
                item_id=103,
                source_item_id=duplicate_source.stable_id,
                source_kind=duplicate_source.kind,
                status=AggregationItemStatus.DUPLICATE.value,
                duplicate_of_item_id=101,
            ),
            SourceExtractionItemResult(
                position=3,
                item_id=104,
                source_item_id=failed_source.stable_id,
                source_kind=failed_source.kind,
                status=AggregationItemStatus.FAILED.value,
            ),
        ]

        agent = MultiSourceAggregationAgent(
            aggregation_session_repo=repo,
            llm_client=None,
        )
        result = await agent.execute(
            MultiSourceAggregationInput(
                session_id=session_id,
                correlation_id="agg-phase7-fallback",
                items=items,
                relationship_signal=AggregationRelationshipSignal(
                    relationship_type="topic_cluster",
                    confidence=0.66,
                    reasoning="Both sources discuss the same launch.",
                ),
            )
        )

        assert result.success is True
        assert isinstance(result.output, MultiSourceAggregationOutput)
        assert result.output.source_type == "mixed"
        assert result.output.used_source_count == 2
        assert len(result.output.key_claims) >= 2
        assert len(result.output.duplicate_signals) == 1
        assert len(result.output.contradictions) == 1
        assert result.output.source_coverage[0].used_in_summary is True
        assert result.output.source_coverage[2].used_in_summary is False
        assert result.output.source_coverage[3].status == AggregationItemStatus.FAILED.value
        assert result.output.relationship_signal is not None
        assert result.output.total_estimated_consumption_time_min == 2

        session = await repo.async_get_aggregation_session(session_id)
        assert session is not None
        assert session["aggregation_output_json"]["source_type"] == "mixed"
        assert (
            session["aggregation_output_json"]["relationship_signal"]["relationship_type"]
            == "topic_cluster"
        )


@pytest.mark.asyncio
async def test_multi_source_aggregation_agent_uses_llm_output_when_available() -> None:
    with temp_db() as db:
        from app.db.models import User

        user = User.create(
            telegram_user_id=987654321,
            username="bundle-user-llm",
            is_owner=True,
        )
        repo = SqliteAggregationSessionRepositoryAdapter(db)
        session_id = await repo.async_create_aggregation_session(
            user_id=user.telegram_user_id,
            correlation_id="agg-phase7-llm",
            total_items=2,
        )

        article_document = _make_document(
            kind=SourceKind.WEB_ARTICLE,
            original_value="https://example.com/analysis",
            title="Policy analysis",
            text="Analysts expect demand to stabilize in the second half of the year.",
        )
        video_document = _make_document(
            kind=SourceKind.YOUTUBE_VIDEO,
            original_value="https://www.youtube.com/watch?v=abc123",
            title="CEO interview",
            text="The CEO said demand should stabilize in the second half of the year.",
            text_kind=ExtractedTextKind.TRANSCRIPT,
            metadata={"estimated_reading_time_min": 3},
        )
        items = [
            SourceExtractionItemResult(
                position=0,
                item_id=201,
                source_item_id=article_document.source_item_id,
                source_kind=article_document.source_kind,
                status=AggregationItemStatus.EXTRACTED.value,
                normalized_document=article_document,
            ),
            SourceExtractionItemResult(
                position=1,
                item_id=202,
                source_item_id=video_document.source_item_id,
                source_kind=video_document.source_kind,
                status=AggregationItemStatus.EXTRACTED.value,
                normalized_document=video_document,
            ),
        ]

        llm_client = MagicMock()
        llm_response = MagicMock()
        llm_response.status = "ok"
        llm_response.response_text = f"""{{
            "overview": "The bundle combines reporting and first-person commentary about stabilizing demand.",
            "key_claims": [
                {{
                    "claim_id": "claim_1",
                    "claim": "Both sources point to demand stabilizing later in the year.",
                    "source_item_ids": ["{article_document.source_item_id}", "{video_document.source_item_id}"],
                    "evidence_kinds": ["text", "transcript"],
                    "confidence": 0.84
                }}
            ],
            "contradictions": [],
            "complementary_points": [
                "The article provides analysis while the video adds executive commentary."
            ],
            "duplicate_signals": [],
            "entities": ["CEO"],
            "topic_tags": ["markets", "#demand"]
        }}"""
        llm_client.chat = AsyncMock(return_value=llm_response)

        agent = MultiSourceAggregationAgent(
            aggregation_session_repo=repo,
            llm_client=llm_client,
        )
        result = await agent.execute(
            MultiSourceAggregationInput(
                session_id=session_id,
                correlation_id="agg-phase7-llm",
                items=items,
            )
        )

        assert result.success is True
        assert result.output is not None
        assert result.output.overview.startswith("The bundle combines reporting")
        assert result.output.key_claims[0].source_item_ids == [
            article_document.source_item_id,
            video_document.source_item_id,
        ]
        assert result.output.key_claims[0].evidence_kinds == [
            AggregationEvidenceKind.TEXT,
            AggregationEvidenceKind.TRANSCRIPT,
        ]
        assert result.output.topic_tags == ["#markets", "#demand"]
        assert result.output.used_source_count == 2
        llm_client.chat.assert_awaited_once()
