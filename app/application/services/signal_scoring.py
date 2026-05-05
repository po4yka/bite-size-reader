"""Cheap Phase 3 signal filtering before LLM-as-judge."""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.core.time_utils import UTC

LLM_JUDGE_CAP_FRACTION = 0.10
MINHASH_SIGNATURE_SIZE = 64
MINHASH_NEAR_DUPLICATE_THRESHOLD = 0.55
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class VectorStoreUnavailableError(RuntimeError):
    """Raised when signal scoring cannot use the required vector similarity store."""


class TopicSimilarityPort(Protocol):
    """Required vector-backed topic similarity port."""

    def is_ready(self) -> bool:
        """Return whether vector topic similarity can serve requests."""

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
            raise VectorStoreUnavailableError(
                "Vector topic similarity is required for signal scoring"
            )

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
                        "minhash_key": _minhash_dedupe_key(candidate),
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
        seen_signatures: list[tuple[int, ...]] = []
        result: list[SignalCandidate] = []
        for candidate in candidates:
            key = self._dedupe_key(candidate)
            if key in seen:
                continue
            signature = _candidate_minhash_signature(candidate)
            if signature and any(
                _signature_similarity(signature, existing) >= MINHASH_NEAR_DUPLICATE_THRESHOLD
                for existing in seen_signatures
            ):
                continue
            seen.add(key)
            if signature:
                seen_signatures.append(signature)
            result.append(candidate)
        return result

    @staticmethod
    def _dedupe_key(candidate: SignalCandidate) -> str:
        if candidate.canonical_url:
            return f"url:{candidate.canonical_url.strip().lower()}"
        minhash_key = _minhash_dedupe_key(candidate)
        if minhash_key:
            return minhash_key
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


def _minhash_dedupe_key(candidate: SignalCandidate) -> str | None:
    signature = _candidate_minhash_signature(candidate)
    if not signature:
        return None
    band_width = 4
    bands = [
        signature[idx : idx + band_width]
        for idx in range(0, len(signature), band_width)
        if len(signature[idx : idx + band_width]) == band_width
    ]
    if not bands:
        return None
    # Use the lowest band hash as a stable near-duplicate bucket.
    band_hashes = [hash(tuple(band)) & 0xFFFFFFFF for band in bands]
    return f"minhash:{min(band_hashes):08x}"


def _candidate_minhash_signature(candidate: SignalCandidate) -> tuple[int, ...] | None:
    text = _candidate_text(candidate)
    shingles = _word_shingles(text)
    if len(shingles) < 3:
        return None
    return _minhash_signature(shingles)


def _candidate_text(candidate: SignalCandidate) -> str:
    metadata_text = candidate.metadata.get("content_text") or candidate.metadata.get("text") or ""
    return " ".join(
        part
        for part in (
            candidate.title or "",
            str(metadata_text or ""),
        )
        if part
    )


def _word_shingles(text: str, *, width: int = 4) -> set[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < width:
        return set(tokens)
    return {" ".join(tokens[idx : idx + width]) for idx in range(len(tokens) - width + 1)}


def _minhash_signature(shingles: set[str]) -> tuple[int, ...]:
    values: list[int] = []
    for seed in range(MINHASH_SIGNATURE_SIZE):
        minimum: int | None = None
        for shingle in shingles:
            digest = hashlib.blake2b(
                f"{seed}:{shingle}".encode(),
                digest_size=8,
            ).digest()
            value = int.from_bytes(digest, byteorder="big")
            if minimum is None or value < minimum:
                minimum = value
        values.append(minimum or 0)
    return tuple(values)


def _signature_similarity(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    matches = sum(1 for lvalue, rvalue in zip(left, right, strict=True) if lvalue == rvalue)
    return matches / len(left)
