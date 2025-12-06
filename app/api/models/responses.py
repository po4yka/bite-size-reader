"""
Pydantic models for API responses.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.context import correlation_id_ctx
from app.core.time_utils import UTC

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_BUILD: str | None = os.getenv("APP_BUILD") or None


class MetaInfo(BaseModel):
    """Metadata for all API responses."""

    correlation_id: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    version: str = APP_VERSION
    build: str | None = APP_BUILD
    pagination: PaginationInfo | None = None
    debug: dict[str, Any] | None = None


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


def _coerce_pagination(pagination: BaseModel | dict[str, Any] | None) -> PaginationInfo | None:
    if pagination is None:
        return None
    if isinstance(pagination, PaginationInfo):
        return pagination
    if isinstance(pagination, BaseModel):
        return PaginationInfo.model_validate(pagination.model_dump())
    return PaginationInfo.model_validate(pagination)


def build_meta(
    *,
    correlation_id: str | None = None,
    pagination: BaseModel | dict[str, Any] | None = None,
    debug: dict[str, Any] | None = None,
    version: str | None = None,
    build: str | None = None,
) -> MetaInfo:
    """Construct meta with sensible defaults and context-aware correlation ID."""
    corr = correlation_id or correlation_id_ctx.get()
    pagination_model = _coerce_pagination(pagination)
    meta_kwargs: dict[str, Any] = {
        "correlation_id": corr,
        "pagination": pagination_model,
        "version": version or APP_VERSION,
        "build": build or APP_BUILD,
    }
    if debug:
        meta_kwargs["debug"] = debug
    return MetaInfo(**meta_kwargs)


def success_response(
    data: BaseModel | dict[str, Any],
    *,
    correlation_id: str | None = None,
    pagination: BaseModel | dict[str, Any] | None = None,
    debug: dict[str, Any] | None = None,
    version: str | None = None,
    build: str | None = None,
) -> dict[str, Any]:
    """Helper to build a standardized success response."""
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    meta = build_meta(
        correlation_id=correlation_id,
        pagination=pagination,
        debug=debug,
        version=version,
        build=build,
    )
    return SuccessResponse(data=payload, meta=meta).model_dump()


def _ensure_error_detail(detail: ErrorDetail, correlation_id: str | None) -> ErrorDetail:
    if detail.correlation_id or not correlation_id:
        return detail
    detail_payload = detail.model_dump()
    detail_payload["correlation_id"] = correlation_id
    return ErrorDetail(**detail_payload)


def error_response(
    detail: ErrorDetail,
    *,
    correlation_id: str | None = None,
    debug: dict[str, Any] | None = None,
    version: str | None = None,
    build: str | None = None,
) -> dict[str, Any]:
    """Helper to build a standardized error response."""
    corr = correlation_id or correlation_id_ctx.get()
    normalized_detail = _ensure_error_detail(detail, corr)
    meta = build_meta(correlation_id=corr, debug=debug, version=version, build=build)
    return ErrorResponse(error=normalized_detail, meta=meta).model_dump()
