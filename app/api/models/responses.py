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
    data: dict[str, Any] | Any
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


class SummaryDetail(BaseModel):
    """Full summary payload with related request/source/processing details."""

    summary: dict[str, Any]
    request: dict[str, Any]
    source: dict[str, Any]
    processing: dict[str, Any]


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


class TokenPair(BaseModel):
    """JWT token pair."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int
    token_type: str = "Bearer"


class AuthTokensResponse(BaseModel):
    """Authentication tokens payload."""

    tokens: TokenPair


class UserInfo(BaseModel):
    """Basic user info."""

    user_id: int
    username: str | None = None
    client_id: str | None = None
    is_owner: bool = False
    created_at: str | None = None


class SubmitRequestData(BaseModel):
    """Wrapper for request submission."""

    request: SubmitRequestResponse


class RequestStatusData(BaseModel):
    """Wrapper for request status polling."""

    status: RequestStatus


class DuplicateCheckData(BaseModel):
    """Duplicate check response."""

    is_duplicate: bool
    normalized_url: str | None = None
    dedupe_hash: str | None = None
    request_id: int | None = None
    summary_id: int | None = None
    summarized_at: str | None = None
    summary: dict[str, Any] | None = None


class SearchResult(BaseModel):
    """Search result payload."""

    request_id: int
    summary_id: int
    url: str | None
    title: str
    domain: str | None = None
    snippet: str | None = None
    tldr: str | None = None
    published_at: str | None = None
    created_at: str
    relevance_score: float | None = None
    topic_tags: list[str] | None = None
    is_read: bool | None = None


class SearchResultsData(BaseModel):
    """Wrapper for search responses."""

    results: list[SearchResult]
    pagination: PaginationInfo
    query: str


class SyncSessionInfo(BaseModel):
    """Sync session metadata."""

    sync_id: str
    timestamp: str
    total_items: int
    chunks: int
    download_urls: list[str]
    expires_at: str


class SyncChunkData(BaseModel):
    """Chunk download payload."""

    sync_id: str
    chunk_number: int
    total_chunks: int
    items: list[dict[str, Any]]


class SyncDeltaData(BaseModel):
    """Delta sync payload."""

    changes: dict[str, list[dict[str, Any]]]
    sync_timestamp: str
    has_more: bool


class SyncUploadResult(BaseModel):
    """Upload local changes result."""

    applied_changes: int
    conflicts: list[dict[str, Any]]
    sync_timestamp: str


class PreferencesData(BaseModel):
    """User preferences payload."""

    user_id: int
    telegram_username: str | None = None
    lang_preference: str | None = None
    notification_settings: dict[str, Any] | None = None
    app_settings: dict[str, Any] | None = None


class PreferencesUpdateResult(BaseModel):
    """Preferences update result."""

    updated_fields: list[str]
    updated_at: str


class UserStatsData(BaseModel):
    """User statistics payload."""

    total_summaries: int
    unread_count: int
    read_count: int
    total_reading_time_min: int
    average_reading_time_min: float
    favorite_topics: list[dict[str, Any]]
    favorite_domains: list[dict[str, Any]]
    language_distribution: dict[str, int]
    joined_at: str | None
    last_summary_at: str | None


def success_response(data: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Helper to build a standardized success response."""
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    return SuccessResponse(data=payload).model_dump()


def error_response(detail: ErrorDetail) -> dict[str, Any]:
    """Helper to build a standardized error response."""
    return ErrorResponse(error=detail).model_dump()
