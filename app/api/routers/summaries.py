"""
Summary management endpoints.

Provides CRUD operations for summaries.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone

from app.api.auth import get_current_user
from app.api.models.requests import UpdateSummaryRequest
from app.api.models.responses import SuccessResponse, SummaryCompact, PaginationInfo
from app.api.services import SummaryService
from app.api.exceptions import ResourceNotFoundError
from app.db.models import Summary, Request as RequestModel, CrawlResult, LLMCall
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("")
async def get_summaries(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_read: Optional[bool] = Query(None),
    lang: Optional[str] = Query(None, pattern="^(en|ru|auto)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    sort: str = Query("created_at_desc", pattern="^(created_at_desc|created_at_asc)$"),
    user=Depends(get_current_user),
):
    """
    Get paginated list of summaries.

    Query Parameters:
    - limit: Items per page (1-100, default 20)
    - offset: Pagination offset (default 0)
    - is_read: Filter by read status (optional)
    - lang: Filter by language (en/ru/auto)
    - start_date: Filter by creation date (ISO 8601)
    - end_date: Filter by creation date (ISO 8601)
    - sort: Sort order (created_at_desc/created_at_asc)
    """
    # Use service layer for business logic
    summaries, total, unread_count = SummaryService.get_user_summaries(
        user_id=user["user_id"],
        limit=limit,
        offset=offset,
        is_read=is_read,
        lang=lang,
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )

    # Build response
    summary_list = []
    for summary in summaries:
        request = summary.request
        json_payload = summary.json_payload or {}
        metadata = json_payload.get("metadata", {})

        summary_list.append(
            SummaryCompact(
                id=summary.id,
                request_id=request.id,
                title=metadata.get("title", "Untitled"),
                domain=metadata.get("domain", ""),
                url=request.input_url or request.normalized_url or "",
                tldr=json_payload.get("tldr", ""),
                summary_250=json_payload.get("summary_250", ""),
                reading_time_min=json_payload.get("estimated_reading_time_min", 0),
                topic_tags=json_payload.get("topic_tags", []),
                is_read=summary.is_read,
                lang=summary.lang or "auto",
                created_at=summary.created_at.isoformat() + "Z",
                confidence=json_payload.get("confidence", 0.0),
                hallucination_risk=json_payload.get("hallucination_risk", "unknown"),
            ).dict()
        )

    return {
        "success": True,
        "data": {
            "summaries": summary_list,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
            "stats": {
                "total_summaries": total,
                "unread_count": unread_count,
            },
        },
    }


@router.get("/{summary_id}")
async def get_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Get a single summary with full details."""
    # Use service layer - it handles authorization and returns summary
    summary = SummaryService.get_summary_by_id(user["user_id"], summary_id)

    # Request is already loaded (eager loading in service)
    request = summary.request

    # Load crawl result and LLM calls
    crawl_result = CrawlResult.select().where(CrawlResult.request == request.id).first()
    llm_calls = list(LLMCall.select().where(LLMCall.request == request.id))

    # Build source metadata
    source = {}
    if crawl_result:
        metadata = crawl_result.metadata_json or {}
        source = {
            "url": crawl_result.source_url,
            "title": metadata.get("title"),
            "domain": metadata.get("domain"),
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "http_status": crawl_result.http_status,
        }

    # Build processing info
    processing = {}
    if llm_calls:
        latest_call = llm_calls[-1]
        processing = {
            "model": latest_call.model,
            "tokens_used": (latest_call.tokens_prompt or 0) + (latest_call.tokens_completion or 0),
            "cost_usd": latest_call.cost_usd,
            "latency_ms": sum(call.latency_ms or 0 for call in llm_calls),
            "crawl_latency_ms": crawl_result.latency_ms if crawl_result else None,
            "llm_latency_ms": latest_call.latency_ms,
        }

    return {
        "success": True,
        "data": {
            "summary": {
                "id": summary.id,
                "request_id": request.id,
                "lang": summary.lang,
                "is_read": summary.is_read,
                "version": summary.version,
                "created_at": summary.created_at.isoformat() + "Z",
                "json_payload": summary.json_payload,
            },
            "request": {
                "id": request.id,
                "type": request.type,
                "status": request.status,
                "input_url": request.input_url,
                "normalized_url": request.normalized_url,
                "correlation_id": request.correlation_id,
                "created_at": request.created_at.isoformat() + "Z",
            },
            "source": source,
            "processing": processing,
        },
    }


@router.patch("/{summary_id}")
async def update_summary(
    summary_id: int,
    update: UpdateSummaryRequest,
    user=Depends(get_current_user),
):
    """Update summary metadata (e.g., mark as read)."""
    # Use service layer
    SummaryService.update_summary(
        user_id=user["user_id"],
        summary_id=summary_id,
        is_read=update.is_read,
    )

    return {
        "success": True,
        "data": {
            "id": summary_id,
            "is_read": update.is_read,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Delete a summary (soft delete)."""
    # Use service layer
    SummaryService.delete_summary(user_id=user["user_id"], summary_id=summary_id)

    return {
        "success": True,
        "data": {
            "id": summary_id,
            "deleted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }
