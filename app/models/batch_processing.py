"""Deprecated compatibility export for batch-processing adapter models."""

from __future__ import annotations

from app.adapter_models.batch_processing import (
    FailedURLDetail,
    URLBatchStatus,
    URLProcessingResult,
    URLStatus,
    URLStatusEntry,
)

__all__ = [
    "FailedURLDetail",
    "URLBatchStatus",
    "URLProcessingResult",
    "URLStatus",
    "URLStatusEntry",
]
