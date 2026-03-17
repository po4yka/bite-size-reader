"""Backward-compat re-export — real implementation in app/application/services/related_reads_service."""

from app.application.services.related_reads_service import (
    RelatedReadItem,
    RelatedReadsService,
    VectorSearchPort,
    _format_age,
)

__all__ = ["RelatedReadItem", "RelatedReadsService", "VectorSearchPort", "_format_age"]
