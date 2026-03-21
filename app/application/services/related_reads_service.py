"""Application service for finding related past summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.embedding_text import prepare_text_for_embedding

if TYPE_CHECKING:
    from app.application.ports import VectorSearchPort


@dataclass(frozen=True)
class RelatedReadItem:
    summary_id: int
    request_id: int
    title: str
    age_label: str
    similarity_score: float


def _format_age(dt: datetime | str | None) -> str:
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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(tz=UTC) - dt
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
    return f"{days // 365}y"


class RelatedReadsService:
    """Find related past summaries using vector similarity."""

    def __init__(
        self,
        vector_search: VectorSearchPort,
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
        del language
        metadata = summary_payload.get("metadata", {}) if isinstance(summary_payload, dict) else {}
        title = metadata.get("title") or summary_payload.get("title")
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

        results = await self._vector_search.search(search_text)
        items: list[RelatedReadItem] = []
        for result in results:
            if result.similarity_score < self._min_similarity:
                continue
            if exclude_request_id is not None and result.request_id == exclude_request_id:
                continue
            items.append(
                RelatedReadItem(
                    summary_id=result.summary_id,
                    request_id=result.request_id,
                    title=result.title or result.url or f"Summary #{result.summary_id}",
                    age_label=_format_age(result.published_at),
                    similarity_score=result.similarity_score,
                )
            )
            if len(items) >= self._max_results:
                break
        return items
