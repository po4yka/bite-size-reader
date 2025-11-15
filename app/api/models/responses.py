"""
Pydantic models for API responses.
"""

from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime


class MetaInfo(BaseModel):
    """Metadata for all API responses."""

    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    version: str = "1.0"


class ErrorDetail(BaseModel):
    """Error details."""

    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""

    success: bool = True
    data: Dict[str, Any]
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
    topic_tags: List[str]
    is_read: bool
    lang: str
    created_at: str
    confidence: float
    hallucination_risk: str


class SummaryListResponse(BaseModel):
    """Response for GET /summaries."""

    summaries: List[SummaryCompact]
    pagination: PaginationInfo
    stats: Dict[str, int]


class RequestStatus(BaseModel):
    """Request processing status."""

    request_id: int
    status: str
    stage: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    estimated_seconds_remaining: Optional[int] = None
    error_message: Optional[str] = None
    can_retry: Optional[bool] = None
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
