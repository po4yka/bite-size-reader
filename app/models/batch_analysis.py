"""Deprecated compatibility export for batch-analysis adapter models."""

from __future__ import annotations

from app.adapter_models.batch_analysis import (
    ArticleMetadata,
    BatchAnalysisResult,
    ClusterInfo,
    CombinedSummaryInput,
    CombinedSummaryOutput,
    RelationshipAnalysisInput,
    RelationshipAnalysisOutput,
    RelationshipType,
    SeriesInfo,
)

__all__ = [
    "ArticleMetadata",
    "BatchAnalysisResult",
    "ClusterInfo",
    "CombinedSummaryInput",
    "CombinedSummaryOutput",
    "RelationshipAnalysisInput",
    "RelationshipAnalysisOutput",
    "RelationshipType",
    "SeriesInfo",
]
