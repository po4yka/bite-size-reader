"""
Summary management endpoints.

Provides CRUD operations for summaries.
"""

from datetime import datetime
from hashlib import sha256

from fastapi import APIRouter, Depends, Query
from peewee import OperationalError

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import UpdateSummaryRequest
from app.api.models.responses import (
    SummaryCompact,
    SummaryContent,
    SummaryContentData,
    SummaryDetail,
    SummaryListResponse,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.api.services import SummaryService
from app.core.html_utils import clean_markdown_article_text, html_to_text
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request as RequestModel, Summary
from app.services.topic_search_utils import ensure_mapping

logger = get_logger(__name__)
router = APIRouter()


def _isotime(dt) -> str:
    """Safely convert datetime to ISO string."""
    if hasattr(dt, "isoformat"):
        return dt.isoformat() + "Z"
    return str(dt)


@router.get("")
async def get_summaries(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_read: bool | None = Query(None),
    is_favorited: bool | None = Query(None),
    lang: str | None = Query(None, pattern="^(en|ru|auto)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
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
        is_favorited=is_favorited,
        lang=lang,
        start_date=start_date,
        end_date=end_date,
        sort=sort,
    )

    # Build response
    summary_list: list[SummaryCompact] = []
    for summary in summaries:
        request = summary.request
        json_payload = ensure_mapping(summary.json_payload)
        metadata = ensure_mapping(json_payload.get("metadata"))

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
                is_favorited=getattr(summary, "is_favorited", False),
                lang=summary.lang or "auto",
                created_at=_isotime(summary.created_at),
                confidence=json_payload.get("confidence", 0.0),
                hallucination_risk=json_payload.get("hallucination_risk", "unknown"),
                image_url=metadata.get("image")
                or metadata.get("og:image")
                or metadata.get("ogImage"),
            )
        )

    pagination = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }

    return success_response(
        SummaryListResponse(
            summaries=summary_list,
            pagination=pagination,
            stats={"total_summaries": total, "unread_count": unread_count},
        ),
        pagination=pagination,
    )


@router.get("/by-url")
async def get_summary_by_url(
    url: str = Query(..., description="Original URL of the article"),
    user=Depends(get_current_user),
):
    """Get a single summary (article) by its original URL."""
    # Try to find request by input_url or normalized_url
    # We join with Summary to ensure a summary actually exists
    request_query = (
        RequestModel.select(RequestModel.id)
        .join(Summary)
        .where(
            (RequestModel.user_id == user["user_id"])
            & ((RequestModel.input_url == url) | (RequestModel.normalized_url == url))
            & (Summary.request == RequestModel.id)
        )
        .order_by(RequestModel.created_at.desc())
        .limit(1)
    )

    request_record = request_query.first()

    if not request_record:
        # Try fuzzy match? Or maybe client sent a slightly different URL.
        # For now, strict match or simple normalization is safer.
        # Could check if url is missing scheme...
        raise ResourceNotFoundError("Article", url)

    # Reuse get_summary logic by ID
    # We first need the summary ID
    summary = Summary.select(Summary.id).where(Summary.request == request_record.id).first()
    if not summary:
        # Should overlap with query above, but safety check
        raise ResourceNotFoundError("Summary", f"request:{request_record.id}")

    return await get_summary(summary_id=summary.id, user=user)


@router.get("/{summary_id}")
async def get_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Get a single summary with full details."""
    # Use service layer - it handles authorization and returns summary
    try:
        summary = SummaryService.get_summary_by_id(user["user_id"], summary_id)
    except (AttributeError, OperationalError) as err:
        if isinstance(err, AttributeError) and "uninitialized Proxy" not in str(err):
            raise
        if isinstance(err, OperationalError) and isinstance(Summary, type):
            raise
        summary = (
            Summary.select(Summary, RequestModel)
            .join(RequestModel)
            .where((Summary.id == summary_id) & (RequestModel.user_id == user["user_id"]))
            .first()
        )
        if summary is None:
            raise ResourceNotFoundError("Summary", summary_id) from err

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
            "image_url": metadata.get("image")
            or metadata.get("og:image")
            or metadata.get("ogImage"),
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

    return success_response(
        SummaryDetail(
            summary={
                "id": summary.id,
                "request_id": request.id,
                "lang": summary.lang,
                "is_read": summary.is_read,
                "is_favorited": getattr(summary, "is_favorited", False),
                "version": summary.version,
                "created_at": _isotime(summary.created_at),
                "json_payload": summary.json_payload,
            },
            request={
                "id": request.id,
                "type": request.type,
                "status": request.status,
                "input_url": request.input_url,
                "normalized_url": request.normalized_url,
                "correlation_id": request.correlation_id,
                "created_at": _isotime(request.created_at),
            },
            source=source,
            processing=processing,
        )
    )


@router.get("/{summary_id}/content")
async def get_summary_content(
    summary_id: int,
    format: str = Query("markdown", pattern="^(markdown|text)$"),
    user=Depends(get_current_user),
):
    """Get full article content for offline reading."""
    summary = SummaryService.get_summary_by_id(user["user_id"], summary_id)

    request = summary.request
    crawl_result = CrawlResult.select().where(CrawlResult.request == request.id).first()

    if not crawl_result:
        raise ResourceNotFoundError("Content", summary_id)

    metadata = ensure_mapping(crawl_result.metadata_json)
    summary_metadata = ensure_mapping(ensure_mapping(summary.json_payload).get("metadata"))
    source_url = crawl_result.source_url or request.input_url or request.normalized_url
    title = metadata.get("title") or summary_metadata.get("title")
    domain = metadata.get("domain") or summary_metadata.get("domain")

    content_source = None
    source_format = None
    content_type = None

    if crawl_result.content_markdown:
        content_source = crawl_result.content_markdown
        source_format = "markdown"
        content_type = "text/markdown"
    elif crawl_result.content_html:
        content_source = crawl_result.content_html
        source_format = "html"
        content_type = "text/html"
    elif request.content_text:
        content_source = request.content_text
        source_format = "text"
        content_type = "text/plain"

    if not content_source:
        raise ResourceNotFoundError("Content", summary_id)

    output_format = format or "markdown"
    content_value = content_source
    content_mime = content_type

    if output_format == "text":
        if source_format == "markdown":
            content_value = clean_markdown_article_text(content_source)
        elif source_format == "html":
            content_value = html_to_text(content_source)
        content_mime = "text/plain"
    # Requested markdown
    elif source_format == "markdown":
        content_value = content_source
        content_mime = "text/markdown"
    elif source_format == "html":
        # Best-effort fallback to text when markdown unavailable
        content_value = html_to_text(content_source)
        content_mime = "text/plain"
        output_format = "text"
    else:
        content_value = content_source
        content_mime = "text/plain"
        output_format = "text"

    checksum = sha256(content_value.encode("utf-8")).hexdigest() if content_value else None
    size_bytes = len(content_value.encode("utf-8")) if content_value else None
    retrieved_dt = (
        getattr(crawl_result, "updated_at", None)
        or getattr(crawl_result, "created_at", None)
        or datetime.now(UTC)
    )

    return success_response(
        SummaryContentData(
            content=SummaryContent(
                summary_id=summary.id,
                request_id=request.id if request else None,
                format=output_format,
                content=content_value,
                content_type=content_mime,
                lang=summary.lang,
                source_url=source_url,
                title=title,
                domain=domain,
                retrieved_at=_isotime(retrieved_dt),
                size_bytes=size_bytes,
                checksum_sha256=checksum,
            )
        )
    )


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

    return success_response(
        {
            "id": summary_id,
            "is_read": update.is_read,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Delete a summary (soft delete)."""
    # Use service layer
    SummaryService.delete_summary(user_id=user["user_id"], summary_id=summary_id)

    return success_response(
        {
            "id": summary_id,
            "deleted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )


@router.post("/{summary_id}/favorite")
async def toggle_favorite(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Toggle the favorite status of a summary."""
    is_favorited = SummaryService.toggle_favorite(user_id=user["user_id"], summary_id=summary_id)
    return success_response({"success": True, "is_favorited": is_favorited})
