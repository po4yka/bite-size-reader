"""
Pydantic models for API responses.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.time_utils import UTC


class MetaInfo(BaseModel):
    """Metadata for all API responses."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    version: str = "1.0"


class ErrorDetail(BaseModel):
    """Error details."""

    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""

    success: bool = True
    data: dict[str, Any]
    meta: MetaInfo = Field(default_factory=MetaInfo)


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""

    success: bool = False
    error: ErrorDetail
    meta: MetaInfo = Field(default_factory=MetaInfo)


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    total: int
    limit: int
    offset: int
    has_more: bool


class SummaryCompact(BaseModel):
    """Compact summary for list views."""

    id: int
    request_id: int
    title: str
    domain: str
    url: str
    tldr: str
    summary_250: str
    reading_time_min: int
    topic_tags: list[str]
    is_read: bool
    lang: str
    created_at: str
    confidence: float
    hallucination_risk: str


class SummaryListResponse(BaseModel):
    """Response for GET /summaries."""

    summaries: list[SummaryCompact]
    pagination: PaginationInfo
    stats: dict[str, int]


class RequestStatus(BaseModel):
    """Request processing status."""

    request_id: int
    status: str
    stage: str | None = None
    progress: dict[str, Any] | None = None
    estimated_seconds_remaining: int | None = None
    error_message: str | None = None
    can_retry: bool | None = None
    updated_at: str


class SubmitRequestResponse(BaseModel):
    """Response for POST /requests."""

    request_id: int
    correlation_id: str
    type: str
    status: str
    estimated_wait_seconds: int
    created_at: str
    is_duplicate: bool = False
