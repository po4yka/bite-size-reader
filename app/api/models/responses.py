"""
Pydantic models for API responses.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Any, Literal

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

    correlation_id: str = ""
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
    error_type: str = Field(default=ErrorType.INTERNAL.value, serialization_alias="errorType")
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None
    correlation_id: str = ""
    retry_after: int | None = None


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
    has_more: bool = Field(serialization_alias="hasMore")


class SummaryCompact(BaseModel):
    """Compact summary for list views."""

    id: int = Field(description="Unique summary identifier")
    request_id: int = Field(serialization_alias="requestId", description="Associated request ID")
    title: str = Field(description="Article title")
    domain: str = Field(description="Source domain (e.g., example.com)")
    url: str = Field(description="Original article URL")
    tldr: str = Field(description="Concise multi-sentence summary")
    summary_250: str = Field(
        serialization_alias="summary250", description="Short summary (<=250 chars)"
    )
    reading_time_min: int = Field(
        serialization_alias="readingTimeMin", description="Estimated reading time in minutes"
    )
    topic_tags: list[str] = Field(serialization_alias="topicTags", description="Topic hashtags")
    is_read: bool = Field(serialization_alias="isRead", description="User read status")
    is_favorited: bool = Field(
        default=False, serialization_alias="isFavorited", description="User favorite status"
    )
    lang: Literal["en", "ru", "auto"] = Field(description="Detected or preferred language")
    created_at: str = Field(
        serialization_alias="createdAt", description="ISO 8601 creation timestamp"
    )
    confidence: float = Field(description="LLM confidence score (0.0-1.0)")
    hallucination_risk: Literal["low", "medium", "high", "unknown"] = Field(
        serialization_alias="hallucinationRisk", description="Assessed hallucination risk level"
    )
    image_url: str | None = Field(
        default=None,
        serialization_alias="imageUrl",
        description="Featured image URL (if available)",
    )


class SummaryDetailEntities(BaseModel):
    """Entity breakdown for summary detail."""

    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class SummaryDetailReadability(BaseModel):
    """Readability metrics."""

    method: str
    score: float
    level: str


class SummaryDetailKeyStat(BaseModel):
    """Key statistic entry."""

    label: str
    value: float
    unit: str
    source_excerpt: str = Field(serialization_alias="sourceExcerpt")


class SummaryDetailSummary(BaseModel):
    """Summary content fields."""

    summary_250: str = Field(serialization_alias="summary250")
    summary_1000: str = Field(serialization_alias="summary1000")
    tldr: str
    key_ideas: list[str] = Field(serialization_alias="keyIdeas")
    topic_tags: list[str] = Field(serialization_alias="topicTags")
    entities: SummaryDetailEntities
    estimated_reading_time_min: int = Field(serialization_alias="estimatedReadingTimeMin")
    key_stats: list[SummaryDetailKeyStat] = Field(
        default_factory=list, serialization_alias="keyStats"
    )
    answered_questions: list[str] = Field(
        default_factory=list, serialization_alias="answeredQuestions"
    )
    readability: SummaryDetailReadability | None = None
    seo_keywords: list[str] = Field(default_factory=list, serialization_alias="seoKeywords")


class SummaryDetailRequest(BaseModel):
    """Request metadata."""

    id: str
    type: str
    url: str | None = None
    normalized_url: str | None = Field(default=None, serialization_alias="normalizedUrl")
    dedupe_hash: str | None = Field(default=None, serialization_alias="dedupeHash")
    status: str
    lang_detected: str | None = Field(default=None, serialization_alias="langDetected")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class SummaryDetailSource(BaseModel):
    """Source content metadata."""

    url: str | None = None
    title: str | None = None
    domain: str | None = None
    author: str | None = None
    published_at: str | None = Field(default=None, serialization_alias="publishedAt")
    word_count: int | None = Field(default=None, serialization_alias="wordCount")
    content_type: str | None = Field(default=None, serialization_alias="contentType")


class SummaryDetailProcessing(BaseModel):
    """Processing metadata."""

    model_used: str | None = Field(default=None, serialization_alias="modelUsed")
    tokens_used: int | None = Field(default=None, serialization_alias="tokensUsed")
    processing_time_ms: int | None = Field(default=None, serialization_alias="processingTimeMs")
    crawl_time_ms: int | None = Field(default=None, serialization_alias="crawlTimeMs")
    confidence: float | None = None
    hallucination_risk: str | None = Field(default=None, serialization_alias="hallucinationRisk")


class SummaryDetail(BaseModel):
    """Full summary payload with related request/source/processing details."""

    summary: SummaryDetailSummary
    request: SummaryDetailRequest
    source: SummaryDetailSource
    processing: SummaryDetailProcessing


class SummaryContent(BaseModel):
    """Full article content for offline reading."""

    summary_id: int = Field(serialization_alias="summaryId")
    request_id: int | None = Field(default=None, serialization_alias="requestId")
    format: Literal["markdown", "text", "html"]
    content: str
    content_type: Literal["text/markdown", "text/plain", "text/html"] = Field(
        serialization_alias="contentType"
    )
    lang: Literal["en", "ru", "auto"] | None = None
    source_url: str | None = Field(default=None, serialization_alias="sourceUrl")
    title: str | None = None
    domain: str | None = None
    retrieved_at: str = Field(serialization_alias="retrievedAt")
    size_bytes: int | None = Field(default=None, serialization_alias="sizeBytes")
    checksum_sha256: str | None = Field(default=None, serialization_alias="checksumSha256")


class SummaryContentData(BaseModel):
    """Wrapper for summary content responses."""

    content: SummaryContent


class SummaryListResponse(BaseModel):
    """Response for GET /summaries."""

    summaries: list[SummaryCompact]
    pagination: PaginationInfo
    stats: dict[str, int]


class RequestStatus(BaseModel):
    """Request processing status with stage-dependent field availability.

    Field Availability by Stage:
    ============================

    PENDING (stage="pending"):
        - request_id: always
        - status: always
        - stage: "pending"
        - queuePosition: present (1-indexed position in queue)
        - canRetry: false
        - correlation_id: always
        - updated_at: always
        - progress: null
        - estimated_seconds_remaining: null
        - error_*: null

    CRAWLING (stage="crawling"):
        - request_id: always
        - status: always
        - stage: "crawling"
        - progress: {current_step: 1, total_steps: 3, percentage: 33}
        - estimated_seconds_remaining: ~8 seconds
        - canRetry: false
        - correlation_id: always
        - updated_at: always
        - queuePosition: null
        - error_*: null

    PROCESSING (stage="processing"):
        - request_id: always
        - status: always
        - stage: "processing"
        - progress: {current_step: 2-3, total_steps: 3, percentage: 66-90}
        - estimated_seconds_remaining: ~8 seconds
        - canRetry: false
        - correlation_id: always
        - updated_at: always
        - queuePosition: null
        - error_*: null

    COMPLETE (stage="complete"):
        - request_id: always
        - status: always
        - stage: "complete"
        - canRetry: false
        - correlation_id: always
        - updated_at: always
        - progress: null
        - estimated_seconds_remaining: null
        - queuePosition: null
        - error_*: null

    FAILED (stage="failed"):
        - request_id: always
        - status: always
        - stage: "failed"
        - error_message: present (human-readable error description)
        - error_stage: present if known (e.g., "crawling", "summarization")
        - error_type: present if known (e.g., "timeout", "rate_limit")
        - canRetry: true (failed requests can be retried)
        - correlation_id: always
        - updated_at: always
        - progress: null
        - estimated_seconds_remaining: null
        - queuePosition: null
    """

    request_id: int = Field(description="Unique request identifier")
    status: str = Field(description="Raw database status value")
    stage: RequestStage = Field(description="Processing stage enum value")
    progress: dict[str, Any] | None = Field(
        default=None,
        description="Progress with current_step, total_steps, percentage",
    )
    estimated_seconds_remaining: int | None = Field(
        default=None,
        description="Estimated time to completion in seconds (crawling/processing only)",
    )
    queue_position: int | None = Field(
        default=None,
        serialization_alias="queuePosition",
        description="1-indexed position in processing queue (pending only)",
    )
    error_stage: str | None = Field(
        default=None,
        description="Stage where error occurred, e.g. 'crawling', 'summarization' (failed only)",
    )
    error_type: str | None = Field(
        default=None,
        description="Error classification e.g. timeout, rate_limit (failed only)",
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable error description (failed only)",
    )
    can_retry: bool = Field(
        default=False,
        serialization_alias="canRetry",
        description="Whether request can be retried (true for failed, false otherwise)",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Request correlation ID for debugging (always present)",
    )
    updated_at: str = Field(description="ISO 8601 timestamp of last status update (always present)")


class SubmitRequestResponse(BaseModel):
    """Response for POST /requests."""

    request_id: int = Field(serialization_alias="requestId")
    correlation_id: str = Field(serialization_alias="correlationId")
    type: Literal["url", "forward"]
    status: Literal["pending", "processing", "complete", "failed"]
    estimated_wait_seconds: int = Field(serialization_alias="estimatedWaitSeconds")
    created_at: str = Field(serialization_alias="createdAt")
    is_duplicate: bool = Field(default=False, serialization_alias="isDuplicate")


class TokenPair(BaseModel):
    """JWT token pair."""

    access_token: str = Field(serialization_alias="accessToken", description="JWT access token")
    refresh_token: str | None = Field(
        default=None,
        serialization_alias="refreshToken",
        description="JWT refresh token (if available)",
    )
    expires_in: int = Field(
        serialization_alias="expiresIn", description="Token expiration time in seconds"
    )
    token_type: str = Field(
        default="Bearer",
        serialization_alias="tokenType",
        description="Token type (always 'Bearer')",
    )


class AuthTokensResponse(BaseModel):
    """Authentication tokens payload."""

    tokens: TokenPair
    session_id: int | None = Field(default=None, serialization_alias="sessionId")


class UserInfo(BaseModel):
    """Basic user info."""

    user_id: int = Field(serialization_alias="userId", description="Unique user identifier")
    username: str = Field(description="Telegram username")
    client_id: str = Field(
        serialization_alias="clientId", description="Client application identifier"
    )
    is_owner: bool = Field(
        default=False, serialization_alias="isOwner", description="Bot owner status"
    )
    created_at: str = Field(
        serialization_alias="createdAt", description="ISO 8601 user registration timestamp"
    )


class SubmitRequestData(BaseModel):
    """Wrapper for request submission."""

    request: SubmitRequestResponse


class RequestStatusData(BaseModel):
    """Wrapper for request status polling."""

    status: RequestStatus


class DuplicateCheckData(BaseModel):
    """Duplicate check response."""

    is_duplicate: bool = Field(serialization_alias="isDuplicate")
    normalized_url: str | None = Field(default=None, serialization_alias="normalizedUrl")
    dedupe_hash: str | None = Field(default=None, serialization_alias="dedupeHash")
    request_id: int | None = Field(default=None, serialization_alias="requestId")
    summary_id: int | None = Field(default=None, serialization_alias="summaryId")
    summarized_at: str | None = Field(default=None, serialization_alias="summarizedAt")
    summary: dict[str, Any] | None = None


class CollectionResponse(BaseModel):
    """Collection details."""

    id: int
    name: str
    description: str | None = None
    parent_id: int | None = Field(default=None, serialization_alias="parentId")
    position: int | None = None
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
    server_version: int = Field(serialization_alias="serverVersion")
    is_shared: bool = Field(default=False, serialization_alias="isShared")
    share_count: int | None = Field(default=None, serialization_alias="shareCount")
    item_count: int | None = Field(default=None, serialization_alias="itemCount")
    children: list[CollectionResponse] | None = None


class CollectionListResponse(BaseModel):
    """List of collections."""

    collections: list[CollectionResponse]
    pagination: PaginationInfo | None = None


class CollectionItem(BaseModel):
    """Collection item entry."""

    collection_id: int = Field(serialization_alias="collectionId")
    summary_id: int = Field(serialization_alias="summaryId")
    position: int | None = None
    created_at: str = Field(serialization_alias="createdAt")


class CollectionItemsResponse(BaseModel):
    """List items in a collection."""

    items: list[CollectionItem]
    pagination: PaginationInfo


class CollectionAclEntry(BaseModel):
    """ACL entry for a collaborator."""

    user_id: int | None = Field(default=None, serialization_alias="userId")
    role: Literal["owner", "editor", "viewer"]
    status: Literal["active", "pending", "revoked"]
    invited_by: int | None = Field(default=None, serialization_alias="invitedBy")
    created_at: str | None = Field(default=None, serialization_alias="createdAt")
    updated_at: str | None = Field(default=None, serialization_alias="updatedAt")


class CollectionAclResponse(BaseModel):
    """ACL listing."""

    acl: list[CollectionAclEntry]


class CollectionInviteResponse(BaseModel):
    """Invite token response."""

    token: str
    role: Literal["editor", "viewer"]
    expires_at: str | None = Field(default=None, serialization_alias="expiresAt")


class CollectionMoveResponse(BaseModel):
    """Response for collection move."""

    id: int
    parent_id: int | None = Field(serialization_alias="parentId")
    position: int
    server_version: int | None = Field(default=None, serialization_alias="serverVersion")
    updated_at: str = Field(serialization_alias="updatedAt")


class CollectionItemsMoveResponse(BaseModel):
    """Response for moving collection items."""

    moved_summary_ids: list[int] = Field(serialization_alias="movedSummaryIds")


# Rebuild forward refs
CollectionResponse.model_rebuild()


class SearchResult(BaseModel):
    """Search result payload."""

    request_id: int = Field(serialization_alias="requestId")
    summary_id: int = Field(serialization_alias="summaryId")
    url: str | None
    title: str
    domain: str | None = None
    snippet: str | None = None
    tldr: str | None = None
    published_at: str | None = Field(default=None, serialization_alias="publishedAt")
    created_at: str = Field(serialization_alias="createdAt")
    relevance_score: float | None = Field(default=None, serialization_alias="relevanceScore")
    topic_tags: list[str] | None = Field(default=None, serialization_alias="topicTags")
    is_read: bool | None = Field(default=None, serialization_alias="isRead")


class SearchResultsData(BaseModel):
    """Wrapper for search responses."""

    results: list[SearchResult]
    pagination: PaginationInfo
    query: str


class SyncSessionData(BaseModel):
    """Sync session metadata (aligned to OpenAPI)."""

    session_id: str = Field(
        serialization_alias="sessionId", description="Unique sync session identifier"
    )
    expires_at: str = Field(
        serialization_alias="expiresAt", description="ISO 8601 session expiration timestamp"
    )
    default_limit: int = Field(
        serialization_alias="defaultLimit", description="Default page size for sync requests"
    )
    max_limit: int = Field(serialization_alias="maxLimit", description="Maximum allowed page size")
    last_issued_since: int | None = Field(
        default=None,
        serialization_alias="lastIssuedSince",
        description="Last issued 'since' value (if any)",
    )


class SyncEntityEnvelope(BaseModel):
    """Envelope for a synced entity or tombstone."""

    entity_type: str = Field(serialization_alias="entityType")
    id: int | str
    server_version: int = Field(serialization_alias="serverVersion")
    updated_at: str = Field(serialization_alias="updatedAt")
    deleted_at: str | None = Field(default=None, serialization_alias="deletedAt")
    summary: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    preference: dict[str, Any] | None = None
    stat: dict[str, Any] | None = None
    crawl_result: dict[str, Any] | None = Field(default=None, serialization_alias="crawlResult")
    llm_call: dict[str, Any] | None = Field(default=None, serialization_alias="llmCall")


class FullSyncResponseData(BaseModel):
    """Response payload for full sync chunks."""

    session_id: str = Field(serialization_alias="sessionId")
    has_more: bool = Field(serialization_alias="hasMore")
    next_since: int | None = Field(default=None, serialization_alias="nextSince")
    items: list[SyncEntityEnvelope]
    pagination: PaginationInfo


class DeltaSyncResponseData(BaseModel):
    """Response payload for delta sync."""

    session_id: str = Field(serialization_alias="sessionId")
    since: int
    has_more: bool = Field(serialization_alias="hasMore")
    next_since: int | None = Field(default=None, serialization_alias="nextSince")
    created: list[SyncEntityEnvelope]
    updated: list[SyncEntityEnvelope]
    deleted: list[SyncEntityEnvelope]


class SyncApplyItemResult(BaseModel):
    """Result for a single applied change."""

    entity_type: str = Field(serialization_alias="entityType")
    id: int | str
    status: Literal["applied", "conflict", "invalid"]
    server_version: int | None = Field(default=None, serialization_alias="serverVersion")
    server_snapshot: dict[str, Any] | None = Field(
        default=None, serialization_alias="serverSnapshot"
    )
    error_code: str | None = Field(default=None, serialization_alias="errorCode")


class SyncApplyResponseData(BaseModel):
    """Upload local changes result (aligned to OpenAPI)."""

    session_id: str = Field(serialization_alias="sessionId")
    results: list[SyncApplyItemResult]
    conflicts: list[SyncApplyItemResult] | None = None
    has_more: bool | None = Field(default=None, serialization_alias="hasMore")


class PreferencesData(BaseModel):
    """User preferences payload."""

    user_id: int = Field(serialization_alias="userId")
    telegram_username: str | None = Field(default=None, serialization_alias="telegramUsername")
    lang_preference: str | None = Field(default=None, serialization_alias="langPreference")
    notification_settings: dict[str, Any] | None = Field(
        default=None, serialization_alias="notificationSettings"
    )
    app_settings: dict[str, Any] | None = Field(default=None, serialization_alias="appSettings")


class PreferencesUpdateResult(BaseModel):
    """Preferences update result."""

    updated_fields: list[str] = Field(serialization_alias="updatedFields")
    updated_at: str = Field(serialization_alias="updatedAt")


class TopicStat(BaseModel):
    """Topic statistics entry."""

    topic: str
    count: int


class DomainStat(BaseModel):
    """Domain statistics entry."""

    domain: str
    count: int


class UserStatsData(BaseModel):
    """User statistics payload."""

    total_summaries: int = Field(serialization_alias="totalSummaries")
    unread_count: int = Field(serialization_alias="unreadCount")
    read_count: int = Field(serialization_alias="readCount")
    total_reading_time_min: int = Field(serialization_alias="totalReadingTimeMin")
    average_reading_time_min: float = Field(serialization_alias="averageReadingTimeMin")
    favorite_topics: list[TopicStat] = Field(serialization_alias="favoriteTopics")
    favorite_domains: list[DomainStat] = Field(serialization_alias="favoriteDomains")
    language_distribution: dict[str, int] = Field(serialization_alias="languageDistribution")
    joined_at: str | None = Field(default=None, serialization_alias="joinedAt")
    last_summary_at: str | None = Field(default=None, serialization_alias="lastSummaryAt")


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
    corr = correlation_id or correlation_id_ctx.get() or ""
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


def _ensure_error_detail(detail: ErrorDetail, correlation_id: str) -> ErrorDetail:
    if detail.correlation_id:
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
    corr = correlation_id or correlation_id_ctx.get() or ""
    normalized_detail = _ensure_error_detail(detail, corr)
    meta = build_meta(correlation_id=corr, debug=debug, version=version, build=build)
    return ErrorResponse(error=normalized_detail, meta=meta).model_dump(by_alias=True)
