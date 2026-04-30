"""Cheap Phase 3 signal filtering before LLM-as-judge."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.core.time_utils import UTC

LLM_JUDGE_CAP_FRACTION = 0.10


class ChromaUnavailableError(RuntimeError):
    """Raised when signal scoring cannot use required Chroma similarity."""


class TopicSimilarityPort(Protocol):
    """Required Chroma-backed topic similarity port."""

    def is_ready(self) -> bool:
        """Return whether Chroma topic similarity can serve requests."""

    async def score_item(self, candidate: SignalCandidate) -> float:
        """Return a normalized topic similarity score for a candidate."""


@dataclass(slots=True, frozen=True)
class SignalCandidate:
    """Input to the deterministic pre-LLM signal scorer."""

    feed_item_id: int
    source_id: int
    source_kind: str
    title: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None
    views: int | None = None
    forwards: int | None = None
    comments: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ScoredSignal:
    """Output from deterministic pre-LLM signal scoring."""

    feed_item_id: int
    score: float
    should_reach_llm_judge: bool
    evidence: dict[str, object]


class SignalScoringService:
    """Score signal candidates and cap LLM judge volume."""

    def __init__(self, *, topic_similarity: TopicSimilarityPort) -> None:
        self._topic_similarity = topic_similarity

    async def score(
        self,
        candidates: list[SignalCandidate],
        *,
        now: datetime | None = None,
    ) -> list[ScoredSignal]:
        if not self._topic_similarity.is_ready():
            raise ChromaUnavailableError("Chroma topic similarity is required for signal scoring")

        now = now or datetime.now(UTC)
        deduped = self._dedupe(candidates)
        source_counts: dict[int, int] = defaultdict(int)
        raw_scores: list[ScoredSignal] = []

        for candidate in deduped:
            source_counts[candidate.source_id] += 1
            recency = self._recency_score(candidate, now)
            engagement = self._engagement_score(candidate)
            topic_similarity = await self._topic_similarity.score_item(candidate)
            diversity_penalty = max(0.0, 1.0 - ((source_counts[candidate.source_id] - 1) * 0.12))
            score = (
                (0.35 * recency)
                + (0.20 * engagement)
                + (0.45 * max(0.0, min(1.0, topic_similarity)))
            ) * diversity_penalty
            raw_scores.append(
                ScoredSignal(
                    feed_item_id=candidate.feed_item_id,
                    score=score,
                    should_reach_llm_judge=False,
                    evidence={
                        "recency_score": recency,
                        "engagement_score": engagement,
                        "topic_similarity_score": topic_similarity,
                        "source_diversity_multiplier": diversity_penalty,
                        "dedupe_key": self._dedupe_key(candidate),
                        "llm_cap_fraction": LLM_JUDGE_CAP_FRACTION,
                    },
                )
            )

        judge_limit = math.floor(len(raw_scores) * LLM_JUDGE_CAP_FRACTION)
        judge_ids = {
            item.feed_item_id
            for item in sorted(raw_scores, key=lambda row: row.score, reverse=True)[:judge_limit]
        }
        return [
            ScoredSignal(
                feed_item_id=item.feed_item_id,
                score=item.score,
                should_reach_llm_judge=item.feed_item_id in judge_ids,
                evidence=item.evidence,
            )
            for item in raw_scores
        ]

    def _dedupe(self, candidates: list[SignalCandidate]) -> list[SignalCandidate]:
        seen: set[str] = set()
        result: list[SignalCandidate] = []
        for candidate in candidates:
            key = self._dedupe_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    @staticmethod
    def _dedupe_key(candidate: SignalCandidate) -> str:
        if candidate.canonical_url:
            return f"url:{candidate.canonical_url.strip().lower()}"
        if candidate.title:
            return f"title:{candidate.title.strip().lower()}"
        return f"item:{candidate.feed_item_id}"

    @staticmethod
    def _recency_score(candidate: SignalCandidate, now: datetime) -> float:
        if candidate.published_at is None:
            return 0.5
        age_hours = max(0.0, (now - candidate.published_at).total_seconds() / 3600.0)
        return max(0.0, 1.0 - (age_hours / (14 * 24)))

    @staticmethod
    def _engagement_score(candidate: SignalCandidate) -> float:
        views = max(0, candidate.views or 0)
        forwards = max(0, candidate.forwards or 0)
        comments = max(0, candidate.comments or 0)
        # Log scale keeps Telegram/HN/Reddit engagement comparable enough for v0.
        weighted = views + (forwards * 25) + (comments * 10)
        if weighted <= 0:
            return 0.0
        return min(1.0, math.log10(weighted + 1) / 4.0)
