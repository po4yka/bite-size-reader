"""Service for finding related past summaries after a new summarization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.services.embedding_service import prepare_text_for_embedding

if TYPE_CHECKING:
    from app.services.vector_search_service import VectorSearchResult, VectorSearchService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelatedReadItem:
    summary_id: int
    request_id: int
    title: str
    age_label: str
    similarity_score: float


def _format_age(dt: datetime | str | None) -> str:
    """Format a datetime as a short relative age label (e.g. '2d', '3w')."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        parsed: datetime | None = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(dt, fmt).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        if parsed is None:
            return ""
        dt = parsed
    now = datetime.now(tz=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    days = max(delta.days, 0)
    if days < 1:
        return "today"
    if days < 7:
        return f"{days}d"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years = days // 365
    return f"{years}y"


class RelatedReadsService:
    """Find related past summaries using vector similarity."""

    def __init__(
        self,
        vector_search: VectorSearchService,
        *,
        min_similarity: float = 0.75,
        max_results: int = 3,
    ) -> None:
        self._vector_search = vector_search
        self._min_similarity = min_similarity
        self._max_results = max_results

    async def find_related(
        self,
        summary_payload: dict[str, Any],
        exclude_request_id: int | None = None,
        language: str | None = None,
    ) -> list[RelatedReadItem]:
        """Find related past summaries for a given summary payload."""
        metadata = summary_payload.get("metadata", {}) if isinstance(summary_payload, dict) else {}
        title = (
            metadata.get("title") or summary_payload.get("title")
            if isinstance(summary_payload, dict)
            else None
        )

        search_text = prepare_text_for_embedding(
            title=title,
            summary_1000=summary_payload.get("summary_1000"),
            summary_250=summary_payload.get("summary_250"),
            tldr=summary_payload.get("tldr"),
            key_ideas=summary_payload.get("key_ideas"),
            topic_tags=summary_payload.get("topic_tags"),
        )
        if not search_text.strip():
            return []

        results: list[VectorSearchResult] = await self._vector_search.search(search_text)

        items: list[RelatedReadItem] = []
        for r in results:
            if r.similarity_score < self._min_similarity:
                continue
            if exclude_request_id is not None and r.request_id == exclude_request_id:
                continue
            age = _format_age(r.published_at)
            items.append(
                RelatedReadItem(
                    summary_id=r.summary_id,
                    request_id=r.request_id,
                    title=r.title or r.url or f"Summary #{r.summary_id}",
                    age_label=age,
                    similarity_score=r.similarity_score,
                )
            )
            if len(items) >= self._max_results:
                break

        return items
