"""DTOs for vector search results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VectorSearchHitDTO:
    request_id: int
    summary_id: int
    similarity_score: float
    url: str | None
    title: str | None
    snippet: str | None
    source: str | None = None
    published_at: str | None = None
