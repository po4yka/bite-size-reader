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
    # Build query with user authorization filter and eager loading
    # Use .select(Summary, RequestModel) to load both in single query (fixes N+1)
    query = (
        Summary.select(Summary, RequestModel)
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])  # Only user's summaries
    )

    # Apply filters
    if is_read is not None:
        query = query.where(Summary.is_read == is_read)

    if lang:
        query = query.where(Summary.lang == lang)

    if start_date:
        query = query.where(RequestModel.created_at >= start_date)

    if end_date:
        query = query.where(RequestModel.created_at <= end_date)

    # Apply sorting
    if sort == "created_at_desc":
        query = query.order_by(RequestModel.created_at.desc())
    else:
        query = query.order_by(RequestModel.created_at.asc())

    # Get total count before pagination
    total = query.count()

    # Apply pagination and execute query
    summaries = list(query.limit(limit).offset(offset))

    # Build response (request is already loaded, no additional queries)
    summary_list = []
    for summary in summaries:
        # Access request without triggering additional query (already eager loaded)
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

    # Get stats (only for current user) - combine into single query using aggregation
    from peewee import fn, Case

    stats_query = (
        Summary.select(
            fn.COUNT(Summary.id).alias("total"),
            fn.SUM(Case(None, [(Summary.is_read == False, 1)], 0)).alias("unread"),
        )
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])
        .first()
    )

    total_summaries = stats_query.total if stats_query else 0
    unread_count = stats_query.unread if stats_query and stats_query.unread else 0

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
                "total_summaries": total_summaries,
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
    # Query with authorization check and eager loading (fixes N+1)
    # Load Summary + Request in single query
    summary = (
        Summary.select(Summary, RequestModel)
        .join(RequestModel)
        .where((Summary.id == summary_id) & (RequestModel.user_id == user["user_id"]))
        .first()
    )

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found or access denied")

    # Request is already loaded (no additional query)
    request = summary.request

    # Load crawl result and LLM calls in separate queries (still better than N queries)
    # These are 1:1 and 1:N relationships, can't be eager loaded with Summary
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
    # Query with authorization check
    summary = (
        Summary.select()
        .join(RequestModel)
        .where((Summary.id == summary_id) & (RequestModel.user_id == user["user_id"]))
        .first()
    )

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found or access denied")

    # Apply updates
    if update.is_read is not None:
        summary.is_read = update.is_read

    summary.save()

    return {
        "success": True,
        "data": {
            "id": summary.id,
            "is_read": summary.is_read,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Delete a summary (soft delete)."""
    # Query with authorization check
    summary = (
        Summary.select()
        .join(RequestModel)
        .where((Summary.id == summary_id) & (RequestModel.user_id == user["user_id"]))
        .first()
    )

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found or access denied")

    # TODO: Implement soft delete (add 'deleted_at' field to model)
    # For now, just mark as read
    summary.is_read = True
    summary.save()

    return {
        "success": True,
        "data": {
            "id": summary.id,
            "deleted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }
