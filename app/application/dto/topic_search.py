"""DTOs for topic search results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TopicArticle(BaseModel):
    """Lightweight representation of a discovered article."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None
