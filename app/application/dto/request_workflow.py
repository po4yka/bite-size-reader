"""DTOs for request workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class DuplicateRequestMatchDTO:
    existing_request_id: int
    existing_summary_id: int | None
    summarized_at: str


@dataclass(frozen=True, slots=True)
class RequestCreatedDTO:
    id: int
    type: str
    status: str
    correlation_id: str | None
    created_at: datetime
    input_url: str | None = None
    normalized_url: str | None = None
    dedupe_hash: str | None = None
    lang_detected: str | None = None
    content_text: str | None = None
    fwd_from_chat_id: int | None = None
    fwd_from_msg_id: int | None = None


@dataclass(frozen=True, slots=True)
class CrawlResultDTO:
    status: str | None = None
    http_status: int | None = None
    latency_ms: int | None = None
    error_text: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class RequestLLMCallDTO:
    id: int
    model: str | None
    status: str | None
    tokens_prompt: int | None
    tokens_completion: int | None
    cost_usd: float | None
    latency_ms: int | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class SummaryRecordDTO:
    id: int
    lang: str | None
    created_at: datetime | None
    json_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RequestDetailsDTO:
    request: RequestCreatedDTO
    crawl_result: CrawlResultDTO | None
    llm_calls: list[RequestLLMCallDTO]
    summary: SummaryRecordDTO | None


@dataclass(frozen=True, slots=True)
class RequestErrorDetailsDTO:
    stage: str | None
    error_type: str | None
    error_message: str | None
    error_reason_code: str | None
    retryable: bool
    debug: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RequestStatusDTO:
    request_id: int
    status: str | None
    stage: str
    progress: dict[str, Any] | None
    estimated_seconds_remaining: int | None
    queue_position: int | None
    error_details: RequestErrorDetailsDTO | None
    can_retry: bool
    correlation_id: str | None
