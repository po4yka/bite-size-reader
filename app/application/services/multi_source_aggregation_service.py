"""Shared workflow for mixed-source extraction plus synthesis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.adapter_models.batch_analysis import ArticleMetadata, RelationshipAnalysisInput
from app.agents.multi_source_aggregation_agent import (
    MultiSourceAggregationAgent,
    MultiSourceAggregationInput,
)
from app.agents.multi_source_extraction_agent import (
    MultiSourceExtractionAgent,
    MultiSourceExtractionInput,
)
from app.agents.relationship_analysis_agent import RelationshipAnalysisAgent
from app.application.dto.aggregation import (
    AggregationFailure,
    AggregationRelationshipSignal,
    MultiSourceAggregationOutput,
    MultiSourceExtractionOutput,
    SourceSubmission,
)
from app.core.logging_utils import get_logger
from app.domain.models.source import AggregationSessionStatus
from app.observability.metrics import record_aggregation_synthesis

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.content.content_extractor import ContentExtractor
    from app.adapters.llm import LLMClientProtocol
    from app.application.ports.aggregation_sessions import AggregationSessionRepositoryPort

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MultiSourceAggregationRunResult:
    """Combined extraction and synthesis outputs for a bundle run."""

    extraction: MultiSourceExtractionOutput
    aggregation: MultiSourceAggregationOutput


class MultiSourceAggregationService:
    """Run the end-to-end bundle workflow over mixed source submissions."""

    def __init__(
        self,
        *,
        content_extractor: ContentExtractor,
        aggregation_session_repo: AggregationSessionRepositoryPort,
        llm_client: LLMClientProtocol | None = None,
    ) -> None:
        self._content_extractor = content_extractor
        self._aggregation_session_repo = aggregation_session_repo
        self._llm = llm_client

    async def aggregate(
        self,
        *,
        correlation_id: str,
        user_id: int,
        submissions: list[SourceSubmission],
        language: str = "en",
        metadata: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> MultiSourceAggregationRunResult:
        """Extract a bundle, derive optional relationship signal, then synthesize."""

        run_started = time.perf_counter()
        extraction_agent = MultiSourceExtractionAgent(
            content_extractor=self._content_extractor,
            aggregation_session_repo=self._aggregation_session_repo,
        )
        extraction_result = await extraction_agent.execute(
            MultiSourceExtractionInput(
                correlation_id=correlation_id,
                user_id=user_id,
                items=submissions,
                metadata=dict(metadata or {}),
                progress_callback=progress_callback,
            )
        )
        if not extraction_result.success or extraction_result.output is None:
            msg = extraction_result.error or "Bundle extraction failed"
            raise RuntimeError(msg)

        try:
            relationship_signal = await self._maybe_build_relationship_signal(
                extraction_result.output,
                correlation_id=correlation_id,
                language=language,
            )
        except Exception:
            logger.exception(
                "relationship_signal_failed",
                extra={"cid": correlation_id},
            )
            relationship_signal = None
        aggregation_agent = MultiSourceAggregationAgent(
            aggregation_session_repo=self._aggregation_session_repo,
            llm_client=self._llm,
        )
        aggregation_result = await aggregation_agent.execute(
            MultiSourceAggregationInput(
                session_id=extraction_result.output.session_id,
                correlation_id=correlation_id,
                items=extraction_result.output.items,
                language=language,
                relationship_signal=relationship_signal,
            )
        )
        if not aggregation_result.success or aggregation_result.output is None:
            record_aggregation_synthesis(
                source_type="unknown",
                bundle_profile=_classify_bundle_profile(extraction_result.output),
                status="failed",
                used_source_count=0,
                coverage_ratio=0.0,
                cost_usd=float(aggregation_result.metadata.get("llm_cost_usd", 0.0)),
            )
            msg = aggregation_result.error or "Bundle aggregation failed"
            await self._aggregation_session_repo.async_update_aggregation_session_status(
                extraction_result.output.session_id,
                status=AggregationSessionStatus.FAILED,
                processing_time_ms=int((time.perf_counter() - run_started) * 1000),
                failure=AggregationFailure(
                    code="aggregation_failed",
                    message=msg,
                    retryable=True,
                    details={
                        "extraction_status": extraction_result.output.status,
                        "successful_count": extraction_result.output.successful_count,
                        "failed_count": extraction_result.output.failed_count,
                    },
                ),
            )
            raise RuntimeError(msg)

        bundle_profile = _classify_bundle_profile(extraction_result.output)
        coverage_ratio = aggregation_result.output.used_source_count / max(
            extraction_result.output.successful_count, 1
        )
        record_aggregation_synthesis(
            source_type=aggregation_result.output.source_type,
            bundle_profile=bundle_profile,
            status=aggregation_result.output.status,
            used_source_count=aggregation_result.output.used_source_count,
            coverage_ratio=coverage_ratio,
            cost_usd=float(aggregation_result.metadata.get("llm_cost_usd", 0.0)),
        )
        await self._aggregation_session_repo.async_update_aggregation_session_status(
            extraction_result.output.session_id,
            status=aggregation_result.output.status,
            processing_time_ms=int((time.perf_counter() - run_started) * 1000),
        )
        return MultiSourceAggregationRunResult(
            extraction=extraction_result.output,
            aggregation=aggregation_result.output,
        )

    async def _maybe_build_relationship_signal(
        self,
        extraction_output: MultiSourceExtractionOutput,
        *,
        correlation_id: str,
        language: str,
    ) -> AggregationRelationshipSignal | None:
        if self._llm is None:
            return None

        articles = self._build_relationship_articles(extraction_output)
        if len(articles) < 2:
            return None

        relationship_agent = RelationshipAnalysisAgent(
            llm_client=self._llm,
            correlation_id=correlation_id,
        )
        relationship_result = await relationship_agent.execute(
            RelationshipAnalysisInput(
                articles=articles,
                correlation_id=correlation_id,
                language=language,
            )
        )
        if not relationship_result.success or relationship_result.output is None:
            return None
        return AggregationRelationshipSignal.from_relationship_analysis(relationship_result.output)

    def _build_relationship_articles(
        self, extraction_output: MultiSourceExtractionOutput
    ) -> list[ArticleMetadata]:
        articles: list[ArticleMetadata] = []
        for item in extraction_output.items:
            document = item.normalized_document
            if document is None or document.provenance.normalized_value is None:
                continue
            url = document.provenance.normalized_value
            entities = _extract_entity_names(document.metadata.get("entities"))
            topic_tags = [
                str(tag).strip()
                for tag in document.metadata.get("topic_tags", [])
                if str(tag).strip()
            ]
            try:
                domain = urlparse(url).netloc
            except ValueError:
                domain = None
            articles.append(
                ArticleMetadata(
                    request_id=item.request_id or item.item_id,
                    url=url,
                    title=document.title,
                    author=_coerce_text(document.metadata.get("author")),
                    domain=domain,
                    published_at=_coerce_text(document.metadata.get("published_at")),
                    topic_tags=topic_tags,
                    entities=entities,
                    summary_250=_truncate(document.text, 250),
                    summary_1000=_truncate(document.text, 1000),
                    language=document.detected_language,
                )
            )
        return articles


def _coerce_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _extract_entity_names(raw_entities: Any) -> list[str]:
    if not isinstance(raw_entities, list):
        return []
    entities: list[str] = []
    for entity in raw_entities:
        if isinstance(entity, dict) and "name" in entity:
            name = str(entity["name"]).strip()
        else:
            name = str(entity).strip()
        if name and name not in entities:
            entities.append(name)
    return entities


def _truncate(text: str, max_length: int) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip()


def _classify_bundle_profile(extraction_output: MultiSourceExtractionOutput) -> str:
    has_video = False
    has_media = False
    for item in extraction_output.items:
        document = item.normalized_document
        if document is None:
            continue
        media_kinds = {asset.kind.value for asset in document.media}
        if "video" in media_kinds:
            has_video = True
        if media_kinds:
            has_media = True
    if has_video:
        return "video_heavy"
    if has_media:
        return "multimodal"
    return "text_only"
