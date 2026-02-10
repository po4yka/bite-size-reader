"""Pydantic models for batch article relationship analysis."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RelationshipType(StrEnum):
    """Types of relationships between batch articles."""

    SERIES = "series"  # Part 1, Part 2, etc. - explicit ordering
    TOPIC_CLUSTER = "topic_cluster"  # Same topic, different perspectives
    AUTHOR_COLLECTION = "author_collection"  # Same author, related content
    DOMAIN_RELATED = "domain_related"  # Same domain, loosely related
    UNRELATED = "unrelated"  # No meaningful relationship detected


class ArticleMetadata(BaseModel):
    """Extracted metadata from a single article for relationship analysis."""

    model_config = ConfigDict(frozen=True)

    request_id: int
    url: str
    title: str | None = None
    author: str | None = None
    domain: str | None = None
    published_at: str | None = None
    topic_tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    summary_250: str | None = None
    summary_1000: str | None = None
    language: str | None = None


class RelationshipAnalysisInput(BaseModel):
    """Input for relationship analysis between batch articles."""

    model_config = ConfigDict(frozen=True)

    articles: list[ArticleMetadata]
    correlation_id: str
    language: str = "en"
    series_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    cluster_threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class SeriesInfo(BaseModel):
    """Information about detected article series."""

    series_title: str | None = None
    article_order: list[int]  # request_ids in order
    numbering_pattern: str | None = None  # e.g., "Part N", "Chapter N"
    confidence: float = Field(ge=0.0, le=1.0)


class ClusterInfo(BaseModel):
    """Information about detected topic cluster."""

    cluster_topic: str | None = None
    shared_entities: list[str] = Field(default_factory=list)
    shared_tags: list[str] = Field(default_factory=list)
    perspectives: list[str] = Field(default_factory=list)  # Different angles/views
    confidence: float = Field(ge=0.0, le=1.0)


class RelationshipAnalysisOutput(BaseModel):
    """Output from relationship analysis."""

    relationship_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    series_info: SeriesInfo | None = None
    cluster_info: ClusterInfo | None = None
    reasoning: str | None = None  # Brief explanation of detection
    signals_used: list[str] = Field(default_factory=list)  # Which signals contributed


class CombinedSummaryInput(BaseModel):
    """Input for generating combined summary across related articles."""

    model_config = ConfigDict(frozen=True)

    articles: list[ArticleMetadata]
    relationship: RelationshipAnalysisOutput
    full_summaries: list[dict[str, Any]]  # Full summary JSON payloads
    correlation_id: str
    language: str = "en"


class CombinedSummaryOutput(BaseModel):
    """Output from combined summary generation."""

    thematic_arc: str  # Overarching narrative across articles
    synthesized_insights: list[str]  # Key insights across all articles
    contradictions: list[str] = Field(default_factory=list)  # Conflicting perspectives
    complementary_points: list[str] = Field(default_factory=list)  # Complementary info
    recommended_reading_order: list[int]  # request_ids in recommended order
    reading_order_rationale: str | None = None
    combined_key_ideas: list[str] = Field(default_factory=list)
    combined_entities: list[str] = Field(default_factory=list)
    combined_topic_tags: list[str] = Field(default_factory=list)
    total_reading_time_min: int | None = None


class BatchAnalysisResult(BaseModel):
    """Complete result of batch analysis including relationship and combined summary."""

    batch_session_id: int
    relationship: RelationshipAnalysisOutput
    combined_summary: CombinedSummaryOutput | None = None
    processing_time_ms: int | None = None
    article_count: int
    successful_count: int
