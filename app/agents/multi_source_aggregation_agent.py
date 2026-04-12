"""Mixed-source synthesis agent for extracted aggregation bundles."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.base_agent import AgentResult, BaseAgent
from app.application.dto.aggregation import (
    AggregatedClaim,
    AggregatedContradiction,
    AggregationEvidenceKind,
    AggregationEvidenceWeight,
    AggregationRelationshipSignal,
    AggregationSourceWeight,
    DuplicateSignal,
    ExtractedTextKind,
    MultiSourceAggregationOutput,
    NormalizedSourceDocument,
    SourceCoverageEntry,
    SourceExtractionItemResult,
)
from app.core.call_status import CallStatus
from app.core.json_utils import extract_json
from app.domain.models.source import AggregationItemStatus

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.adapters.llm import LLMClientProtocol
    from app.application.ports.aggregation_sessions import AggregationSessionRepositoryPort

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_HASHTAG_RE = re.compile(r"(?<!\w)#([a-z0-9_-]+)", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "with",
}
_EVIDENCE_BASE_WEIGHTS: dict[AggregationEvidenceKind, float] = {
    AggregationEvidenceKind.TEXT: 1.0,
    AggregationEvidenceKind.TRANSCRIPT: 0.85,
    AggregationEvidenceKind.IMAGE: 0.6,
    AggregationEvidenceKind.OCR: 0.45,
    AggregationEvidenceKind.METADATA: 0.35,
}


class MultiSourceAggregationInput(BaseModel):
    """Input contract for mixed-source bundle synthesis."""

    model_config = ConfigDict(frozen=True)

    session_id: int
    correlation_id: str
    items: list[SourceExtractionItemResult]
    language: str = "en"
    relationship_signal: AggregationRelationshipSignal | None = None

    @model_validator(mode="after")
    def validate_items(self) -> MultiSourceAggregationInput:
        if not self.items:
            msg = "Multi-source aggregation requires at least one bundle item"
            raise ValueError(msg)
        return self


class MultiSourceAggregationAgent(
    BaseAgent[MultiSourceAggregationInput, MultiSourceAggregationOutput]
):
    """Synthesize normalized bundle items into one provenance-aware output."""

    def __init__(
        self,
        *,
        aggregation_session_repo: AggregationSessionRepositoryPort,
        llm_client: LLMClientProtocol | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(name="MultiSourceAggregationAgent", correlation_id=correlation_id)
        self._aggregation_session_repo = aggregation_session_repo
        self._llm = llm_client

    async def execute(
        self, input_data: MultiSourceAggregationInput
    ) -> AgentResult[MultiSourceAggregationOutput]:
        """Generate one mixed-source synthesis output from extracted bundle items."""

        self.correlation_id = input_data.correlation_id
        extracted_items = [
            item
            for item in input_data.items
            if item.status == AggregationItemStatus.EXTRACTED.value and item.normalized_document
        ]
        if not extracted_items:
            return AgentResult.error_result(
                "Cannot synthesize bundle without extracted source documents",
                session_id=input_data.session_id,
            )

        self.log_info(
            "multi_source_aggregation_started",
            session_id=input_data.session_id,
            extracted_items=len(extracted_items),
            total_items=len(input_data.items),
        )

        source_weights = [self._build_source_weight(item) for item in extracted_items]
        weight_by_source_id = {weight.source_item_id: weight for weight in source_weights}
        duplicate_signals = self._detect_duplicate_signals(extracted_items)
        contradiction_hints = self._detect_contradiction_hints(extracted_items)

        output = await self._generate_with_llm(
            input_data=input_data,
            extracted_items=extracted_items,
            source_weights=source_weights,
            duplicate_signals=duplicate_signals,
            contradiction_hints=contradiction_hints,
        )
        if output is None:
            output = self._build_fallback_output(
                input_data=input_data,
                extracted_items=extracted_items,
                source_weights=source_weights,
                duplicate_signals=duplicate_signals,
                contradiction_hints=contradiction_hints,
            )

        coverage = self._build_source_coverage(
            items=input_data.items,
            output=output,
            weight_by_source_id=weight_by_source_id,
        )
        used_source_count = sum(1 for entry in coverage if entry.used_in_summary)
        source_type = self._resolve_source_type(extracted_items)
        total_estimated_consumption_time_min = self._estimate_consumption_time_minutes(
            extracted_items
        )
        output = output.model_copy(
            update={
                "source_type": source_type,
                "used_source_count": used_source_count,
                "source_coverage": coverage,
                "total_estimated_consumption_time_min": total_estimated_consumption_time_min,
            }
        )

        await self._aggregation_session_repo.async_update_aggregation_session_output(
            input_data.session_id,
            output.model_dump(mode="json"),
        )
        return AgentResult.success_result(
            output,
            session_id=input_data.session_id,
            used_source_count=used_source_count,
            source_type=source_type,
        )

    async def _generate_with_llm(
        self,
        *,
        input_data: MultiSourceAggregationInput,
        extracted_items: list[SourceExtractionItemResult],
        source_weights: list[AggregationSourceWeight],
        duplicate_signals: list[DuplicateSignal],
        contradiction_hints: list[AggregatedContradiction],
    ) -> MultiSourceAggregationOutput | None:
        if self._llm is None:
            return None

        prompt = self._load_prompt(input_data.language)
        context = self._build_llm_context(
            input_data=input_data,
            extracted_items=extracted_items,
            source_weights=source_weights,
            duplicate_signals=duplicate_signals,
            contradiction_hints=contradiction_hints,
        )
        result = await self._llm.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
            max_tokens=2400,
            temperature=0.2,
            request_id=None,
        )
        if result.status != CallStatus.OK:
            self.log_warning("multi_source_aggregation_llm_failed", error=result.error_text)
            return None

        parsed = extract_json(result.response_text or "")
        if not isinstance(parsed, dict):
            self.log_warning("multi_source_aggregation_llm_invalid_json")
            return None

        try:
            return self._parse_llm_output(
                parsed=parsed,
                input_data=input_data,
                extracted_items=extracted_items,
                source_weights=source_weights,
                fallback_duplicates=duplicate_signals,
                fallback_contradictions=contradiction_hints,
            )
        except Exception as exc:
            self.log_warning("multi_source_aggregation_llm_parse_failed", error=str(exc))
            return None

    def _parse_llm_output(
        self,
        *,
        parsed: dict[str, Any],
        input_data: MultiSourceAggregationInput,
        extracted_items: list[SourceExtractionItemResult],
        source_weights: list[AggregationSourceWeight],
        fallback_duplicates: list[DuplicateSignal],
        fallback_contradictions: list[AggregatedContradiction],
    ) -> MultiSourceAggregationOutput:
        valid_source_ids = {
            item.normalized_document.source_item_id
            for item in extracted_items
            if item.normalized_document is not None
        }
        claims = self._parse_claims(parsed.get("key_claims"), valid_source_ids)
        if not claims:
            claims = self._fallback_claims(extracted_items, source_weights)

        contradictions = self._parse_contradictions(
            parsed.get("contradictions"),
            valid_source_ids,
        )
        if not contradictions:
            contradictions = fallback_contradictions

        duplicate_signals = self._parse_duplicate_signals(
            parsed.get("duplicate_signals"),
            valid_source_ids,
        )
        if not duplicate_signals:
            duplicate_signals = fallback_duplicates

        overview = str(parsed.get("overview") or "").strip()
        if not overview:
            overview = self._build_overview(extracted_items)

        complementary_points = [
            str(point).strip()
            for point in parsed.get("complementary_points", [])
            if str(point).strip()
        ]
        entities = self._clean_string_list(parsed.get("entities"))
        topic_tags = self._normalize_tags(parsed.get("topic_tags"))

        return MultiSourceAggregationOutput(
            session_id=input_data.session_id,
            correlation_id=input_data.correlation_id,
            status="completed",
            source_type=self._resolve_source_type(extracted_items),
            total_items=len(input_data.items),
            extracted_items=len(extracted_items),
            used_source_count=0,
            overview=overview,
            key_claims=claims,
            contradictions=contradictions,
            complementary_points=complementary_points,
            duplicate_signals=duplicate_signals,
            source_weights=source_weights,
            source_coverage=[],
            relationship_signal=input_data.relationship_signal,
            entities=entities,
            topic_tags=topic_tags,
            total_estimated_consumption_time_min=self._estimate_consumption_time_minutes(
                extracted_items
            ),
        )

    def _build_fallback_output(
        self,
        *,
        input_data: MultiSourceAggregationInput,
        extracted_items: list[SourceExtractionItemResult],
        source_weights: list[AggregationSourceWeight],
        duplicate_signals: list[DuplicateSignal],
        contradiction_hints: list[AggregatedContradiction],
    ) -> MultiSourceAggregationOutput:
        return MultiSourceAggregationOutput(
            session_id=input_data.session_id,
            correlation_id=input_data.correlation_id,
            status="completed",
            source_type=self._resolve_source_type(extracted_items),
            total_items=len(input_data.items),
            extracted_items=len(extracted_items),
            used_source_count=0,
            overview=self._build_overview(extracted_items),
            key_claims=self._fallback_claims(extracted_items, source_weights),
            contradictions=contradiction_hints,
            complementary_points=self._build_complementary_points(extracted_items),
            duplicate_signals=duplicate_signals,
            source_weights=source_weights,
            source_coverage=[],
            relationship_signal=input_data.relationship_signal,
            entities=self._extract_entities_from_documents(extracted_items),
            topic_tags=self._extract_tags_from_documents(extracted_items),
            total_estimated_consumption_time_min=self._estimate_consumption_time_minutes(
                extracted_items
            ),
            metadata={"generation_mode": "heuristic_fallback"},
        )

    def _build_llm_context(
        self,
        *,
        input_data: MultiSourceAggregationInput,
        extracted_items: list[SourceExtractionItemResult],
        source_weights: list[AggregationSourceWeight],
        duplicate_signals: list[DuplicateSignal],
        contradiction_hints: list[AggregatedContradiction],
    ) -> str:
        source_context = []
        for item, weight in zip(extracted_items, source_weights, strict=True):
            document = item.normalized_document
            if document is None:
                continue
            source_context.append(
                {
                    "position": item.position,
                    "source_item_id": document.source_item_id,
                    "source_kind": document.source_kind.value,
                    "title": document.title,
                    "text": self._document_snippet(document),
                    "text_blocks": [
                        {
                            "kind": block.kind.value,
                            "text": self._truncate(block.text, 280),
                            "confidence": block.confidence,
                        }
                        for block in document.text_blocks[:8]
                    ],
                    "media_count": len(document.media),
                    "metadata": self._select_metadata(document.metadata),
                    "weight": weight.model_dump(mode="json"),
                }
            )

        payload = {
            "correlation_id": input_data.correlation_id,
            "language": input_data.language,
            "relationship_signal": input_data.relationship_signal.model_dump(mode="json")
            if input_data.relationship_signal
            else None,
            "duplicate_signals": [signal.model_dump(mode="json") for signal in duplicate_signals],
            "contradiction_hints": [
                contradiction.model_dump(mode="json") for contradiction in contradiction_hints
            ],
            "source_weighting_rules": {
                kind.value: weight for kind, weight in _EVIDENCE_BASE_WEIGHTS.items()
            },
            "sources": source_context,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_source_weight(self, item: SourceExtractionItemResult) -> AggregationSourceWeight:
        document = item.normalized_document
        if document is None:
            msg = "Expected normalized document for extracted item"
            raise ValueError(msg)

        evidence_weights: list[AggregationEvidenceWeight] = []
        if self._has_text_evidence(document):
            evidence_weights.append(
                AggregationEvidenceWeight(
                    kind=AggregationEvidenceKind.TEXT,
                    weight=_EVIDENCE_BASE_WEIGHTS[AggregationEvidenceKind.TEXT],
                    rationale="Primary article or caption/body text is present.",
                )
            )
        if self._has_transcript_evidence(document):
            evidence_weights.append(
                AggregationEvidenceWeight(
                    kind=AggregationEvidenceKind.TRANSCRIPT,
                    weight=_EVIDENCE_BASE_WEIGHTS[AggregationEvidenceKind.TRANSCRIPT],
                    rationale="Transcript content can support time-based media claims.",
                )
            )
        if self._has_image_evidence(document):
            evidence_weights.append(
                AggregationEvidenceWeight(
                    kind=AggregationEvidenceKind.IMAGE,
                    weight=_EVIDENCE_BASE_WEIGHTS[AggregationEvidenceKind.IMAGE],
                    rationale="Media or alt-text adds non-textual context.",
                )
            )
        if self._has_ocr_evidence(document):
            evidence_weights.append(
                AggregationEvidenceWeight(
                    kind=AggregationEvidenceKind.OCR,
                    weight=_EVIDENCE_BASE_WEIGHTS[AggregationEvidenceKind.OCR],
                    rationale="OCR-derived text is lower confidence than authored text.",
                )
            )
        if self._has_metadata_evidence(document):
            evidence_weights.append(
                AggregationEvidenceWeight(
                    kind=AggregationEvidenceKind.METADATA,
                    weight=_EVIDENCE_BASE_WEIGHTS[AggregationEvidenceKind.METADATA],
                    rationale="Structured metadata can anchor titles, IDs, and authorship.",
                )
            )

        total_weight = round(sum(entry.weight for entry in evidence_weights), 2)
        return AggregationSourceWeight(
            source_item_id=document.source_item_id,
            source_kind=document.source_kind,
            total_weight=total_weight,
            evidence_weights=evidence_weights,
            rationale="Higher weight is assigned to authored text, then transcript/media, then OCR/metadata.",
        )

    def _build_source_coverage(
        self,
        *,
        items: list[SourceExtractionItemResult],
        output: MultiSourceAggregationOutput,
        weight_by_source_id: dict[str, AggregationSourceWeight],
    ) -> list[SourceCoverageEntry]:
        claim_ids_by_source: dict[str, list[str]] = defaultdict(list)
        contradiction_count_by_source: dict[str, int] = defaultdict(int)
        duplicate_count_by_source: dict[str, int] = defaultdict(int)

        for claim in output.key_claims:
            for source_item_id in claim.source_item_ids:
                claim_ids_by_source[source_item_id].append(claim.claim_id)

        for contradiction in output.contradictions:
            for source_item_id in contradiction.source_item_ids:
                contradiction_count_by_source[source_item_id] += 1

        for signal in output.duplicate_signals:
            for source_item_id in signal.source_item_ids:
                duplicate_count_by_source[source_item_id] += 1

        coverage: list[SourceCoverageEntry] = []
        for item in items:
            source_item_id = item.source_item_id
            claim_ids = (
                claim_ids_by_source.get(source_item_id, [])
                if item.status != AggregationItemStatus.DUPLICATE.value
                else []
            )
            contradiction_count = (
                contradiction_count_by_source.get(source_item_id, 0)
                if item.status != AggregationItemStatus.DUPLICATE.value
                else 0
            )
            duplicate_signal_count = duplicate_count_by_source.get(source_item_id, 0)
            used_in_summary = item.status != AggregationItemStatus.DUPLICATE.value and bool(
                claim_ids or contradiction_count or duplicate_signal_count
            )
            coverage.append(
                SourceCoverageEntry(
                    position=item.position,
                    item_id=item.item_id,
                    source_item_id=source_item_id,
                    source_kind=item.source_kind,
                    status=item.status,
                    used_in_summary=used_in_summary,
                    claim_ids=claim_ids,
                    contradiction_count=contradiction_count,
                    duplicate_signal_count=duplicate_signal_count,
                    total_weight=weight_by_source_id.get(source_item_id).total_weight
                    if source_item_id in weight_by_source_id
                    else None,
                )
            )
        return coverage

    def _parse_claims(
        self,
        raw_claims: Any,
        valid_source_ids: set[str],
    ) -> list[AggregatedClaim]:
        if not isinstance(raw_claims, list):
            return []

        claims: list[AggregatedClaim] = []
        for index, raw_claim in enumerate(raw_claims, 1):
            if not isinstance(raw_claim, dict):
                continue
            text = str(raw_claim.get("claim") or raw_claim.get("text") or "").strip()
            source_item_ids = self._filter_source_item_ids(
                raw_claim.get("source_item_ids"),
                valid_source_ids,
            )
            if not text or not source_item_ids:
                continue
            evidence_kinds = self._parse_evidence_kinds(raw_claim.get("evidence_kinds"))
            confidence = raw_claim.get("confidence")
            claims.append(
                AggregatedClaim(
                    claim_id=str(raw_claim.get("claim_id") or f"claim_{index}"),
                    text=text,
                    source_item_ids=source_item_ids,
                    evidence_kinds=evidence_kinds,
                    confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                )
            )
        return claims

    def _parse_contradictions(
        self,
        raw_contradictions: Any,
        valid_source_ids: set[str],
    ) -> list[AggregatedContradiction]:
        if not isinstance(raw_contradictions, list):
            return []

        contradictions: list[AggregatedContradiction] = []
        for raw_contradiction in raw_contradictions:
            if not isinstance(raw_contradiction, dict):
                continue
            source_item_ids = self._filter_source_item_ids(
                raw_contradiction.get("source_item_ids"),
                valid_source_ids,
            )
            summary = str(
                raw_contradiction.get("summary") or raw_contradiction.get("text") or ""
            ).strip()
            if not summary or len(source_item_ids) < 2:
                continue
            contradictions.append(
                AggregatedContradiction(
                    summary=summary,
                    source_item_ids=source_item_ids,
                    resolution_note=str(raw_contradiction.get("resolution_note") or "").strip()
                    or None,
                )
            )
        return contradictions

    def _parse_duplicate_signals(
        self,
        raw_signals: Any,
        valid_source_ids: set[str],
    ) -> list[DuplicateSignal]:
        if not isinstance(raw_signals, list):
            return []

        signals: list[DuplicateSignal] = []
        for raw_signal in raw_signals:
            if not isinstance(raw_signal, dict):
                continue
            source_item_ids = self._filter_source_item_ids(
                raw_signal.get("source_item_ids"),
                valid_source_ids,
            )
            summary = str(raw_signal.get("summary") or raw_signal.get("text") or "").strip()
            if not summary or len(source_item_ids) < 2:
                continue
            signals.append(DuplicateSignal(summary=summary, source_item_ids=source_item_ids))
        return signals

    def _fallback_claims(
        self,
        extracted_items: list[SourceExtractionItemResult],
        source_weights: list[AggregationSourceWeight],
    ) -> list[AggregatedClaim]:
        weights_by_source = {weight.source_item_id: weight for weight in source_weights}
        sorted_items = sorted(
            extracted_items,
            key=lambda item: weights_by_source[item.source_item_id].total_weight,
            reverse=True,
        )
        claims: list[AggregatedClaim] = []
        for index, item in enumerate(sorted_items[:5], 1):
            document = item.normalized_document
            if document is None:
                continue
            snippet = self._best_claim_snippet(document)
            if not snippet:
                continue
            weight = weights_by_source[document.source_item_id]
            claims.append(
                AggregatedClaim(
                    claim_id=f"claim_{index}",
                    text=snippet,
                    source_item_ids=[document.source_item_id],
                    evidence_kinds=[entry.kind for entry in weight.evidence_weights],
                    confidence=min(1.0, round(weight.total_weight / 2.5, 2)),
                )
            )
        return claims

    def _build_overview(self, extracted_items: list[SourceExtractionItemResult]) -> str:
        kinds = sorted({item.source_kind.value for item in extracted_items})
        titles = [
            document.title
            for item in extracted_items
            if (document := item.normalized_document) is not None and document.title
        ]
        title_fragment = ", ".join(titles[:3]) if titles else "multiple source items"
        kind_fragment = ", ".join(kinds[:4])
        return (
            f"This bundle synthesizes {len(extracted_items)} extracted sources across {kind_fragment}. "
            f"Primary coverage comes from {title_fragment}."
        )

    def _build_complementary_points(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> list[str]:
        points: list[str] = []
        kinds = {item.source_kind for item in extracted_items}
        if len(kinds) > 1:
            points.append(
                "The bundle combines multiple source types, allowing text, media, and platform context to reinforce each other."
            )
        if any(self._has_image_evidence(item.normalized_document) for item in extracted_items):
            points.append(
                "Visual evidence supplements the authored text, which helps preserve context that a text-only summary would drop."
            )
        if any(self._has_transcript_evidence(item.normalized_document) for item in extracted_items):
            points.append(
                "Transcript evidence adds spoken context that can confirm or expand on captions and titles."
            )
        return points[:4]

    def _detect_duplicate_signals(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> list[DuplicateSignal]:
        sentence_sources: dict[str, set[str]] = defaultdict(set)
        sentence_examples: dict[str, str] = {}
        for item in extracted_items:
            document = item.normalized_document
            if document is None:
                continue
            for sentence in self._document_sentences(document):
                canonical = self._canonical_sentence(sentence)
                if len(canonical.split()) < 6:
                    continue
                sentence_sources[canonical].add(document.source_item_id)
                sentence_examples.setdefault(canonical, sentence.strip())

        duplicate_signals: list[DuplicateSignal] = []
        for canonical, source_ids in sentence_sources.items():
            if len(source_ids) < 2:
                continue
            duplicate_signals.append(
                DuplicateSignal(
                    summary=self._truncate(sentence_examples[canonical], 160),
                    source_item_ids=sorted(source_ids),
                )
            )
        duplicate_signals.sort(key=lambda signal: (-len(signal.source_item_ids), signal.summary))
        return duplicate_signals[:5]

    def _detect_contradiction_hints(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> list[AggregatedContradiction]:
        sentence_groups: dict[str, list[tuple[str, str, tuple[str, ...]]]] = defaultdict(list)
        for item in extracted_items:
            document = item.normalized_document
            if document is None:
                continue
            for sentence in self._document_sentences(document):
                numbers = tuple(sorted(_NUMBER_RE.findall(sentence)))
                if len(numbers) == 0:
                    continue
                base = self._numeric_sentence_base(sentence)
                if len(base.split()) < 4:
                    continue
                sentence_groups[base].append((document.source_item_id, sentence.strip(), numbers))

        contradictions: list[AggregatedContradiction] = []
        for grouped_sentences in sentence_groups.values():
            distinct_numbers = {entry[2] for entry in grouped_sentences}
            if len(distinct_numbers) < 2:
                continue
            source_item_ids = sorted({entry[0] for entry in grouped_sentences})
            if len(source_item_ids) < 2:
                continue
            example_sentences = "; ".join(
                self._truncate(entry[1], 120) for entry in grouped_sentences[:2]
            )
            contradictions.append(
                AggregatedContradiction(
                    summary=f"Potential numeric disagreement detected: {example_sentences}",
                    source_item_ids=source_item_ids,
                    resolution_note="Verify the conflicting figures against the highest-weight sources.",
                )
            )
        return contradictions[:4]

    def _resolve_source_type(self, extracted_items: Iterable[SourceExtractionItemResult]) -> str:
        kinds = sorted(
            {
                item.source_kind.value
                for item in extracted_items
                if item.status == AggregationItemStatus.EXTRACTED.value
            }
        )
        if len(kinds) == 1:
            return kinds[0]
        return "mixed"

    def _estimate_consumption_time_minutes(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> int | None:
        total_minutes = 0
        for item in extracted_items:
            document = item.normalized_document
            if document is None:
                continue
            metadata_minutes = self._coerce_int(
                document.metadata.get("estimated_reading_time_min")
                or document.metadata.get("reading_time_min")
            )
            if metadata_minutes is not None:
                total_minutes += metadata_minutes
                continue
            duration_seconds = 0.0
            for asset in document.media:
                if asset.duration_sec:
                    duration_seconds = max(duration_seconds, float(asset.duration_sec))
            if duration_seconds > 0:
                total_minutes += max(1, round(duration_seconds / 60))
                continue
            word_count = len(document.text.split())
            if word_count > 0:
                total_minutes += max(1, round(word_count / 220))
        return total_minutes or None

    def _extract_entities_from_documents(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> list[str]:
        entities: list[str] = []
        for item in extracted_items:
            document = item.normalized_document
            if document is None:
                continue
            raw_entities = document.metadata.get("entities")
            if not isinstance(raw_entities, list):
                continue
            for entity in raw_entities:
                if isinstance(entity, dict) and "name" in entity:
                    entities.append(str(entity["name"]))
                elif isinstance(entity, str):
                    entities.append(entity)
        return self._clean_string_list(entities)

    def _extract_tags_from_documents(
        self, extracted_items: list[SourceExtractionItemResult]
    ) -> list[str]:
        tags: list[str] = []
        for item in extracted_items:
            document = item.normalized_document
            if document is None:
                continue
            raw_tags = document.metadata.get("topic_tags")
            if isinstance(raw_tags, list):
                tags.extend(str(tag) for tag in raw_tags if str(tag).strip())
            tags.extend(
                f"#{match.group(1).lower()}" for match in _HASHTAG_RE.finditer(document.text)
            )
        return self._normalize_tags(tags)

    def _document_sentences(self, document: NormalizedSourceDocument) -> list[str]:
        sentences: list[str] = []
        if document.title:
            sentences.append(document.title)
        for block in document.text_blocks:
            sentences.extend(
                sentence.strip()
                for sentence in _SENTENCE_SPLIT_RE.split(block.text)
                if sentence.strip()
            )
        if not sentences and document.text.strip():
            sentences.extend(
                sentence.strip()
                for sentence in _SENTENCE_SPLIT_RE.split(document.text)
                if sentence.strip()
            )
        return sentences

    def _document_snippet(self, document: NormalizedSourceDocument) -> str:
        if document.text.strip():
            return self._truncate(document.text, 900)
        snippets = [block.text for block in document.text_blocks if block.text.strip()]
        return self._truncate(" ".join(snippets), 900)

    def _best_claim_snippet(self, document: NormalizedSourceDocument) -> str:
        preferred_kinds = (
            ExtractedTextKind.BODY,
            ExtractedTextKind.CAPTION,
            ExtractedTextKind.TRANSCRIPT,
            ExtractedTextKind.OCR,
            ExtractedTextKind.TITLE,
        )
        for preferred_kind in preferred_kinds:
            for block in document.text_blocks:
                if block.kind != preferred_kind:
                    continue
                sentence = next(
                    (
                        candidate
                        for candidate in self._document_sentences(
                            document.model_copy(update={"text_blocks": [block], "text": block.text})
                        )
                        if len(candidate.split()) >= 6
                    ),
                    None,
                )
                if sentence:
                    return self._truncate(sentence, 220)
        if document.title:
            return self._truncate(document.title, 220)
        return self._truncate(document.text, 220)

    def _parse_evidence_kinds(self, raw_kinds: Any) -> list[AggregationEvidenceKind]:
        if not isinstance(raw_kinds, list):
            return []
        evidence_kinds: list[AggregationEvidenceKind] = []
        for raw_kind in raw_kinds:
            try:
                evidence_kind = AggregationEvidenceKind(str(raw_kind).strip().lower())
            except ValueError:
                continue
            if evidence_kind not in evidence_kinds:
                evidence_kinds.append(evidence_kind)
        return evidence_kinds

    def _filter_source_item_ids(self, raw_source_ids: Any, valid_source_ids: set[str]) -> list[str]:
        if not isinstance(raw_source_ids, list):
            return []
        source_item_ids: list[str] = []
        for raw_source_id in raw_source_ids:
            source_item_id = str(raw_source_id).strip()
            if (
                source_item_id
                and source_item_id in valid_source_ids
                and source_item_id not in source_item_ids
            ):
                source_item_ids.append(source_item_id)
        return source_item_ids

    def _clean_string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        cleaned: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    def _normalize_tags(self, values: Any) -> list[str]:
        tags: list[str] = []
        for value in self._clean_string_list(values):
            normalized = value if value.startswith("#") else f"#{value}"
            normalized = normalized.lower()
            if normalized not in tags:
                tags.append(normalized)
        return tags[:15]

    def _select_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "author",
            "channel",
            "published_at",
            "source",
            "content_source",
            "extraction_strategy",
            "quality_tier",
        )
        selected = {key: metadata[key] for key in keys if key in metadata}
        if "topic_tags" in metadata:
            selected["topic_tags"] = metadata["topic_tags"]
        if "entities" in metadata:
            selected["entities"] = metadata["entities"]
        return selected

    def _has_text_evidence(self, document: NormalizedSourceDocument | None) -> bool:
        if document is None:
            return False
        return any(
            block.kind
            in {ExtractedTextKind.BODY, ExtractedTextKind.CAPTION, ExtractedTextKind.TITLE}
            for block in document.text_blocks
        ) or bool(document.text.strip())

    def _has_transcript_evidence(self, document: NormalizedSourceDocument | None) -> bool:
        if document is None:
            return False
        return any(block.kind == ExtractedTextKind.TRANSCRIPT for block in document.text_blocks)

    def _has_ocr_evidence(self, document: NormalizedSourceDocument | None) -> bool:
        if document is None:
            return False
        return any(block.kind == ExtractedTextKind.OCR for block in document.text_blocks)

    def _has_image_evidence(self, document: NormalizedSourceDocument | None) -> bool:
        if document is None:
            return False
        return bool(document.media)

    def _has_metadata_evidence(self, document: NormalizedSourceDocument | None) -> bool:
        if document is None:
            return False
        return bool(document.metadata or document.title or document.provenance.external_id)

    def _canonical_sentence(self, sentence: str) -> str:
        lowered = sentence.lower()
        lowered = _NON_WORD_RE.sub(" ", lowered)
        return " ".join(lowered.split())

    def _numeric_sentence_base(self, sentence: str) -> str:
        without_numbers = _NUMBER_RE.sub(" ", sentence.lower())
        without_numbers = _NON_WORD_RE.sub(" ", without_numbers)
        tokens = [token for token in without_numbers.split() if token not in _STOPWORDS]
        return " ".join(tokens)

    def _load_prompt(self, language: str) -> str:
        lang = language.lower() if language.lower() in ("en", "ru") else "en"
        prompt_file = _PROMPT_DIR / f"multi_source_aggregation_system_{lang}.txt"
        try:
            return prompt_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (_PROMPT_DIR / "multi_source_aggregation_system_en.txt").read_text(
                encoding="utf-8"
            )

    @staticmethod
    def _truncate(value: str, max_length: int) -> str:
        stripped = value.strip()
        if len(stripped) <= max_length:
            return stripped
        return f"{stripped[: max_length - 1].rstrip()}…"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return coerced if coerced >= 0 else None


__all__ = [
    "MultiSourceAggregationAgent",
    "MultiSourceAggregationInput",
]
