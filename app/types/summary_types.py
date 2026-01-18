"""TypedDict definitions for summary JSON structures.

These types provide improved type safety for summary data throughout the codebase,
replacing generic dict[str, Any] with structured types.
"""

from __future__ import annotations

from typing import TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing import NotRequired


class KeyStat(TypedDict):
    """Key statistic entry from the summary."""

    label: str
    value: float | int
    unit: str | None
    source_excerpt: str | None


class Entities(TypedDict):
    """Named entities extracted from the content."""

    people: list[str]
    organizations: list[str]
    locations: list[str]


class Readability(TypedDict):
    """Readability metrics for the content."""

    method: str
    score: float
    level: str


class Metadata(TypedDict):
    """Article metadata from the source."""

    title: str | None
    canonical_url: str | None
    domain: str | None
    author: str | None
    published_at: str | None
    last_updated: str | None


class SemanticChunk(TypedDict):
    """Semantic chunk for search indexing."""

    article_id: str | None
    section: str | None
    language: str | None
    topics: list[str]
    text: str
    local_summary: str | None
    local_keywords: list[str]


class SummaryDict(TypedDict, total=False):
    """Complete summary structure.

    Required fields:
        summary_250: Short summary (max 250 chars)
        summary_1000: Full summary (max 1000 chars)
        tldr: Concise multi-sentence summary
        key_ideas: List of key ideas
        topic_tags: Topic hashtags
        entities: Named entities
        estimated_reading_time_min: Reading time estimate

    Optional fields:
        key_stats: Key statistics
        answered_questions: Questions answered by the article
        readability: Readability metrics
        seo_keywords: SEO keywords
        query_expansion_keywords: Keywords for search expansion
        semantic_boosters: Semantic search boosters
        semantic_chunks: Semantic chunks for search
        article_id: Unique article identifier
        metadata: Article metadata
    """

    # Required fields
    summary_250: str
    summary_1000: str
    tldr: str
    key_ideas: list[str]
    topic_tags: list[str]
    entities: Entities
    estimated_reading_time_min: int

    # Optional fields
    key_stats: NotRequired[list[KeyStat]]
    answered_questions: NotRequired[list[str]]
    readability: NotRequired[Readability]
    seo_keywords: NotRequired[list[str]]
    query_expansion_keywords: NotRequired[list[str]]
    semantic_boosters: NotRequired[list[str]]
    semantic_chunks: NotRequired[list[SemanticChunk]]
    article_id: NotRequired[str | None]
    metadata: NotRequired[Metadata]
