"""Tests for Phase 3 cheap signal filtering."""

from __future__ import annotations

import datetime as dt

import pytest

from app.application.services.signal_scoring import (
    SignalCandidate,
    SignalScoringService,
    VectorStoreUnavailableError,
)
from app.core.time_utils import UTC


class _FakeTopicSimilarity:
    def __init__(self, scores: dict[int, float], *, ready: bool = True) -> None:
        self._scores = scores
        self._ready = ready

    def is_ready(self) -> bool:
        return self._ready

    async def score_item(self, candidate: SignalCandidate) -> float:
        return self._scores.get(candidate.feed_item_id, 0.0)


@pytest.mark.asyncio
async def test_signal_scoring_rejects_90_percent_before_llm_judge():
    now = dt.datetime(2026, 4, 30, tzinfo=UTC)
    candidates = [
        SignalCandidate(
            feed_item_id=i,
            source_id=i % 4,
            source_kind="telegram_channel",
            title=f"Item {i}",
            canonical_url=f"https://example.com/{i}",
            published_at=now - dt.timedelta(hours=i),
            views=i * 10,
            forwards=i,
        )
        for i in range(20)
    ]
    service = SignalScoringService(topic_similarity=_FakeTopicSimilarity({19: 1.0, 18: 0.9}))

    scored = await service.score(candidates, now=now)

    assert len(scored) == 20
    assert sum(item.should_reach_llm_judge for item in scored) == 2
    assert sum(not item.should_reach_llm_judge for item in scored) == 18
    assert all(item.evidence["llm_cap_fraction"] == 0.1 for item in scored)


@pytest.mark.asyncio
async def test_signal_scoring_fails_closed_when_vector_store_unavailable():
    candidate = SignalCandidate(
        feed_item_id=1,
        source_id=1,
        source_kind="rss",
        title="Item",
        canonical_url="https://example.com/1",
    )
    service = SignalScoringService(topic_similarity=_FakeTopicSimilarity({}, ready=False))

    with pytest.raises(VectorStoreUnavailableError):
        await service.score([candidate])


@pytest.mark.asyncio
async def test_signal_scoring_dedupes_exact_url_and_title_candidates():
    now = dt.datetime(2026, 4, 30, tzinfo=UTC)
    candidates = [
        SignalCandidate(
            feed_item_id=1,
            source_id=1,
            source_kind="rss",
            title="Same title",
            canonical_url="https://example.com/post",
            published_at=now,
        ),
        SignalCandidate(
            feed_item_id=2,
            source_id=2,
            source_kind="rss",
            title="Same title",
            canonical_url="https://example.com/post",
            published_at=now,
        ),
    ]
    service = SignalScoringService(topic_similarity=_FakeTopicSimilarity({1: 1.0, 2: 1.0}))

    scored = await service.score(candidates, now=now)

    assert [item.feed_item_id for item in scored] == [1]
    assert scored[0].evidence["dedupe_key"] == "url:https://example.com/post"


@pytest.mark.asyncio
async def test_signal_scoring_dedupes_near_duplicate_text_with_minhash():
    now = dt.datetime(2026, 4, 30, tzinfo=UTC)
    candidates = [
        SignalCandidate(
            feed_item_id=1,
            source_id=1,
            source_kind="rss",
            title="Python packaging migration guide",
            canonical_url="https://example.com/a",
            published_at=now,
            metadata={
                "content_text": "Python packaging migration guide for teams moving from setup.py"
            },
        ),
        SignalCandidate(
            feed_item_id=2,
            source_id=2,
            source_kind="rss",
            title="Python packaging migration guide for teams",
            canonical_url="https://example.net/b",
            published_at=now,
            metadata={
                "content_text": "A Python packaging migration guide for teams moving from setup.py"
            },
        ),
    ]
    service = SignalScoringService(topic_similarity=_FakeTopicSimilarity({1: 1.0, 2: 1.0}))

    scored = await service.score(candidates, now=now)

    assert [item.feed_item_id for item in scored] == [1]
    assert str(scored[0].evidence["minhash_key"]).startswith("minhash:")
