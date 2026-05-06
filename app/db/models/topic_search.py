"""PostgreSQL full-text topic search model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Computed, Index, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TopicSearchIndex(Base):
    __tablename__ = "topic_search_index"
    __table_args__ = (Index("ix_topic_search_body_tsv", "body_tsv", postgresql_using="gin"),)

    request_id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', "
            "coalesce(title,'') || ' ' || coalesce(body,'') || ' ' || coalesce(tags,''))",
            persisted=True,
        ),
    )


TOPIC_SEARCH_MODELS = (TopicSearchIndex,)

__all__ = ["TOPIC_SEARCH_MODELS", "TopicSearchIndex"]
