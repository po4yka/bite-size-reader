"""
Pydantic models for API responses.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.api.context import correlation_id_ctx
from app.core.time_utils import UTC


class ErrorType(str, Enum):
    """Categories of errors for client handling."""

    AUTHENTICATION = "authentication"  # Auth failures, token issues
    AUTHORIZATION = "authorization"  # Permission denied, access control
    VALIDATION = "validation"  # Invalid input, schema errors
    NOT_FOUND = "not_found"  # Resource doesn't exist
    CONFLICT = "conflict"  # Duplicate, version mismatch
    RATE_LIMIT = "rate_limit"  # Too many requests
    EXTERNAL_SERVICE = "external_service"  # Firecrawl, OpenRouter failures
    INTERNAL = "internal"  # Server errors, unexpected failures


class ErrorCode(str, Enum):
    """Structured error codes for programmatic handling."""

    # Authentication errors
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    AUTH_CREDENTIALS_INVALID = "AUTH_CREDENTIALS_INVALID"
    AUTH_SECRET_LOCKED = "AUTH_SECRET_LOCKED"
    AUTH_SECRET_REVOKED = "AUTH_SECRET_REVOKED"

    # Authorization errors
    AUTHZ_USER_NOT_ALLOWED = "AUTHZ_USER_NOT_ALLOWED"
    AUTHZ_CLIENT_NOT_ALLOWED = "AUTHZ_CLIENT_NOT_ALLOWED"
    AUTHZ_OWNER_REQUIRED = "AUTHZ_OWNER_REQUIRED"
    AUTHZ_ACCESS_DENIED = "AUTHZ_ACCESS_DENIED"

    # Validation errors
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_FIELD_REQUIRED = "VALIDATION_FIELD_REQUIRED"
    VALIDATION_FIELD_INVALID = "VALIDATION_FIELD_INVALID"
    VALIDATION_URL_INVALID = "VALIDATION_URL_INVALID"

    # Resource errors
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_VERSION_CONFLICT = "RESOURCE_VERSION_CONFLICT"

    # Rate limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # External service errors
    EXTERNAL_FIRECRAWL_ERROR = "EXTERNAL_FIRECRAWL_ERROR"
    EXTERNAL_OPENROUTER_ERROR = "EXTERNAL_OPENROUTER_ERROR"
    EXTERNAL_TELEGRAM_ERROR = "EXTERNAL_TELEGRAM_ERROR"
    EXTERNAL_SERVICE_TIMEOUT = "EXTERNAL_SERVICE_TIMEOUT"
    EXTERNAL_SERVICE_UNAVAILABLE = "EXTERNAL_SERVICE_UNAVAILABLE"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERNAL_DATABASE_ERROR = "INTERNAL_DATABASE_ERROR"
    INTERNAL_CONFIG_ERROR = "INTERNAL_CONFIG_ERROR"


class RequestStage(str, Enum):
    """Processing stages for request status polling."""

    PENDING = "pending"  # Request queued, waiting to start
    CRAWLING = "crawling"  # Fetching content from URL
    PROCESSING = "processing"  # LLM summarization in progress
    COMPLETE = "complete"  # Successfully finished
    FAILED = "failed"  # Processing failed (check error fields)


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
    """Error details aligned to API error envelope."""

    code: str
    error_type: str = Field(default=ErrorType.INTERNAL.value, alias="errorType")
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None
    correlation_id: str | None = None
    retry_after: int | None = None

    model_config = {"populate_by_name": True}


class SuccessResponse(BaseModel):
    """Standard success response wrapper.

    When success=True, data is always present and non-null.
    """

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
    is_favorited: bool = False
    lang: str
    created_at: str
    confidence: float
    hallucination_risk: str
    image_url: str | None = None


class SummaryDetail(BaseModel):
    """Full summary payload with related request/source/processing details."""

    summary: dict[str, Any]
    request: dict[str, Any]
    source: dict[str, Any]
    processing: dict[str, Any]


class SummaryContent(BaseModel):
    """Full article content for offline reading."""

    summary_id: int
    request_id: int | None = None
    format: str
    content: str
    content_type: str
    lang: str | None = None
    source_url: str | None = None
    title: str | None = None
    domain: str | None = None
    retrieved_at: str
    size_bytes: int | None = None
    checksum_sha256: str | None = None


class SummaryContentData(BaseModel):
    """Wrapper for summary content responses."""

    content: SummaryContent


class SummaryListResponse(BaseModel):
    """Response for GET /summaries."""

    summaries: list[SummaryCompact]
    pagination: PaginationInfo
    stats: dict[str, int]


class RequestStatus(BaseModel):
    """Request processing status."""

    request_id: int
    status: str
    stage: str  # RequestStage enum value: pending, crawling, processing, complete, failed
    progress: dict[str, Any] | None = None
    estimated_seconds_remaining: int | None = None
    queue_position: int | None = Field(
        default=None,
        alias="queuePosition",
        description="Position in queue (only present when stage=pending)",
    )
    error_stage: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    can_retry: bool = Field(default=False, alias="canRetry")
    correlation_id: str | None = None
    updated_at: str

    model_config = {"populate_by_name": True}


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
    session_id: int | None = None


class UserInfo(BaseModel):
    """Basic user info."""

    user_id: int
    username: str
    client_id: str
    is_owner: bool = False
    created_at: str


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


class CollectionResponse(BaseModel):
    """Collection details."""

    id: int
    name: str
    description: str | None = None
    parent_id: int | None = None
    position: int | None = None
    created_at: str
    updated_at: str
    server_version: int
    is_shared: bool = False
    share_count: int | None = None
    item_count: int | None = None
    children: list[CollectionResponse] | None = None


class CollectionListResponse(BaseModel):
    """List of collections."""

    collections: list[CollectionResponse]
    pagination: PaginationInfo | None = None


class CollectionItem(BaseModel):
    """Collection item entry."""

    collection_id: int
    summary_id: int
    position: int | None = None
    created_at: str


class CollectionItemsResponse(BaseModel):
    """List items in a collection."""

    items: list[CollectionItem]
    pagination: PaginationInfo


class CollectionAclEntry(BaseModel):
    """ACL entry for a collaborator."""

    user_id: int | None = None
    role: str
    status: str
    invited_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CollectionAclResponse(BaseModel):
    """ACL listing."""

    acl: list[CollectionAclEntry]


class CollectionInviteResponse(BaseModel):
    """Invite token response."""

    token: str
    role: str
    expires_at: str | None = None


class CollectionMoveResponse(BaseModel):
    """Response for collection move."""

    id: int
    parent_id: int | None
    position: int
    server_version: int | None = None
    updated_at: str


class CollectionItemsMoveResponse(BaseModel):
    """Response for moving collection items."""

    moved_summary_ids: list[int]


# Rebuild forward refs
CollectionResponse.model_rebuild()


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


class SyncSessionData(BaseModel):
    """Sync session metadata (aligned to OpenAPI)."""

    session_id: str
    expires_at: str
    default_limit: int
    max_limit: int
    last_issued_since: int | None = None


class SyncEntityEnvelope(BaseModel):
    """Envelope for a synced entity or tombstone."""

    entity_type: str
    id: int | str
    server_version: int
    updated_at: str
    deleted_at: str | None = None
    summary: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    preference: dict[str, Any] | None = None
    stat: dict[str, Any] | None = None
    crawl_result: dict[str, Any] | None = None
    llm_call: dict[str, Any] | None = None


class FullSyncResponseData(BaseModel):
    """Response payload for full sync chunks."""

    session_id: str
    has_more: bool
    next_since: int | None = None
    items: list[SyncEntityEnvelope]
    pagination: PaginationInfo


class DeltaSyncResponseData(BaseModel):
    """Response payload for delta sync."""

    session_id: str
    since: int
    has_more: bool
    next_since: int | None = None
    created: list[SyncEntityEnvelope]
    updated: list[SyncEntityEnvelope]
    deleted: list[SyncEntityEnvelope]


class SyncApplyItemResult(BaseModel):
    """Result for a single applied change."""

    entity_type: str
    id: int | str
    status: str  # applied | conflict | invalid
    server_version: int | None = None
    server_snapshot: dict[str, Any] | None = None
    error_code: str | None = None


class SyncApplyResponseData(BaseModel):
    """Upload local changes result (aligned to OpenAPI)."""

    session_id: str
    results: list[SyncApplyItemResult]
    conflicts: list[SyncApplyItemResult] | None = None
    has_more: bool | None = None


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


def make_error(
    code: str | ErrorCode,
    message: str,
    *,
    error_type: str | ErrorType | None = None,
    retryable: bool | None = None,
    details: dict[str, Any] | None = None,
    retry_after: int | None = None,
) -> ErrorDetail:
    """
    Create an ErrorDetail with proper typing and defaults.

    Args:
        code: Error code (use ErrorCode enum for standard codes)
        message: Human-readable error message
        error_type: Error category (auto-inferred from code if not provided)
        retryable: Whether client should retry (auto-inferred if not provided)
        details: Additional error context
        retry_after: Seconds to wait before retry (for rate limits)

    Returns:
        Properly typed ErrorDetail
    """
    code_str = code.value if isinstance(code, ErrorCode) else code

    # Auto-infer error_type from code prefix if not provided
    if error_type is None:
        if code_str.startswith("AUTH_"):
            error_type = ErrorType.AUTHENTICATION
        elif code_str.startswith("AUTHZ_"):
            error_type = ErrorType.AUTHORIZATION
        elif code_str.startswith("VALIDATION_"):
            error_type = ErrorType.VALIDATION
        elif code_str.startswith("RESOURCE_NOT_FOUND"):
            error_type = ErrorType.NOT_FOUND
        elif code_str.startswith("RESOURCE_"):
            error_type = ErrorType.CONFLICT
        elif code_str.startswith("RATE_LIMIT"):
            error_type = ErrorType.RATE_LIMIT
        elif code_str.startswith("EXTERNAL_"):
            error_type = ErrorType.EXTERNAL_SERVICE
        else:
            error_type = ErrorType.INTERNAL

    error_type_str = error_type.value if isinstance(error_type, ErrorType) else error_type

    # Auto-infer retryable if not provided
    if retryable is None:
        retryable = error_type_str in (
            ErrorType.RATE_LIMIT.value,
            ErrorType.EXTERNAL_SERVICE.value,
        ) or code_str in (
            ErrorCode.AUTH_SESSION_EXPIRED.value,
            ErrorCode.EXTERNAL_SERVICE_TIMEOUT.value,
            ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE.value,
        )

    return ErrorDetail(
        code=code_str,
        error_type=error_type_str,
        message=message,
        retryable=retryable,
        details=details,
        retry_after=retry_after,
    )


def _ensure_error_detail(detail: ErrorDetail, correlation_id: str | None) -> ErrorDetail:
    if detail.correlation_id or not correlation_id:
        return detail
    detail_payload = detail.model_dump(by_alias=True)
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
    return ErrorResponse(error=normalized_detail, meta=meta).model_dump(by_alias=True)
