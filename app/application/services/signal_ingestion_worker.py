"""Continuous signal ingestion worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.application.services.signal_scoring import (
    ChromaUnavailableError,
    SignalCandidate,
    SignalScoringService,
)
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    from app.application.ports.signal_sources import SignalSourceRepositoryPort

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SignalIngestionStats:
    candidates: int
    persisted: int
    errors: int
    disabled: bool = False

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "candidates": self.candidates,
            "persisted": self.persisted,
            "errors": self.errors,
            "disabled": self.disabled,
        }


class SignalIngestionWorker:
    """Load unscored feed items, score them, and persist user signal rows."""

    def __init__(
        self,
        *,
        repository: SignalSourceRepositoryPort,
        scorer: SignalScoringService,
    ) -> None:
        self._repository = repository
        self._scorer = scorer

    async def run_once(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> dict[str, int | bool]:
        rows = await self._repository.async_list_unscored_candidates(limit=limit)
        candidates = [self._candidate_from_row(row) for row in rows]
        try:
            scored = await self._scorer.score(candidates, now=now)
        except ChromaUnavailableError:
            logger.warning("signal_ingestion_disabled_chroma_unavailable")
            return SignalIngestionStats(
                candidates=len(candidates),
                persisted=0,
                errors=0,
                disabled=True,
            ).to_dict()

        scored_by_item = {item.feed_item_id: item for item in scored}
        persisted = 0
        errors = 0
        for row in rows:
            score = scored_by_item.get(int(row["feed_item_id"]))
            if score is None:
                continue
            try:
                await self._repository.async_record_user_signal(
                    user_id=int(row["user_id"]),
                    feed_item_id=int(row["feed_item_id"]),
                    status="candidate",
                    heuristic_score=score.score,
                    final_score=score.score,
                    evidence=score.evidence,
                    filter_stage="heuristic",
                )
                persisted += 1
            except Exception:
                errors += 1
                logger.warning(
                    "signal_ingestion_persist_failed",
                    extra={
                        "user_id": row.get("user_id"),
                        "feed_item_id": row.get("feed_item_id"),
                    },
                    exc_info=True,
                )

        return SignalIngestionStats(
            candidates=len(candidates),
            persisted=persisted,
            errors=errors,
        ).to_dict()

    @staticmethod
    def _candidate_from_row(row: dict[str, Any]) -> SignalCandidate:
        return SignalCandidate(
            feed_item_id=int(row["feed_item_id"]),
            source_id=int(row["source_id"]),
            source_kind=str(row["source_kind"]),
            title=row.get("title"),
            canonical_url=row.get("canonical_url"),
            published_at=row.get("published_at"),
            views=row.get("views"),
            forwards=row.get("forwards"),
            comments=row.get("comments"),
            metadata={"content_text": row.get("content_text")},
        )
