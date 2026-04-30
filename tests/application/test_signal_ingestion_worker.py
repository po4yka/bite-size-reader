"""Tests for the continuous signal ingestion worker."""

from __future__ import annotations

import datetime as dt

import pytest

from app.application.services.signal_ingestion_worker import SignalIngestionWorker
from app.application.services.signal_scoring import SignalCandidate, SignalScoringService
from app.core.time_utils import UTC


class _FakeTopicSimilarity:
    def is_ready(self) -> bool:
        return True

    async def score_item(self, candidate: SignalCandidate) -> float:
        return 0.9 if candidate.feed_item_id == 1 else 0.2


class _FakeSignalRepository:
    def __init__(self) -> None:
        self.recorded: list[dict] = []

    async def async_list_unscored_candidates(self, *, limit: int = 100) -> list[dict]:
        return [
            {
                "user_id": 1001,
                "feed_item_id": 1,
                "source_id": 10,
                "source_kind": "rss",
                "title": "Python post",
                "canonical_url": "https://example.com/1",
                "content_text": "Python content",
                "published_at": dt.datetime(2026, 4, 30, tzinfo=UTC),
                "views": 100,
                "forwards": 4,
                "comments": None,
            },
            {
                "user_id": 1001,
                "feed_item_id": 2,
                "source_id": 10,
                "source_kind": "rss",
                "title": "Other post",
                "canonical_url": "https://example.com/2",
                "content_text": "Other content",
                "published_at": dt.datetime(2026, 4, 30, tzinfo=UTC),
                "views": None,
                "forwards": None,
                "comments": None,
            },
        ]

    async def async_record_user_signal(self, **kwargs):
        self.recorded.append(dict(kwargs))
        return {"id": len(self.recorded), **kwargs}


@pytest.mark.asyncio
async def test_signal_ingestion_worker_scores_and_persists_candidates() -> None:
    repo = _FakeSignalRepository()
    worker = SignalIngestionWorker(
        repository=repo,
        scorer=SignalScoringService(topic_similarity=_FakeTopicSimilarity()),
    )

    stats = await worker.run_once(limit=10, now=dt.datetime(2026, 4, 30, tzinfo=UTC))

    assert stats == {"candidates": 2, "persisted": 2, "errors": 0, "disabled": False}
    assert [row["feed_item_id"] for row in repo.recorded] == [1, 2]
    assert repo.recorded[0]["status"] == "candidate"
    assert repo.recorded[0]["filter_stage"] == "heuristic"
    assert repo.recorded[0]["final_score"] > repo.recorded[1]["final_score"]


@pytest.mark.asyncio
async def test_signal_ingestion_worker_disables_when_scoring_is_not_ready() -> None:
    class NotReadySimilarity:
        def is_ready(self) -> bool:
            return False

        async def score_item(self, candidate: SignalCandidate) -> float:
            return 0.0

    repo = _FakeSignalRepository()
    worker = SignalIngestionWorker(
        repository=repo,
        scorer=SignalScoringService(topic_similarity=NotReadySimilarity()),
    )

    stats = await worker.run_once()

    assert stats == {"candidates": 2, "persisted": 0, "errors": 0, "disabled": True}
    assert repo.recorded == []
