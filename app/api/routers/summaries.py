"""
Summary management endpoints.

Provides CRUD operations for summaries.
"""

from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Query

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import UpdateSummaryRequest
from app.api.models.responses import (
    DeleteSummaryResponse,
    PaginationInfo,
    SummaryCompact,
    SummaryContent,
    SummaryContentData,
    SummaryDetail,
    SummaryDetailProcessing,
    SummaryDetailRequest,
    SummaryDetailSource,
    SummaryDetailSummary,
    SummaryListResponse,
    SummaryListStats,
    ToggleFavoriteResponse,
    UpdateSummaryResponse,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.api.services import SummaryService
from app.core.html_utils import clean_markdown_article_text, html_to_text
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.services.topic_search_utils import ensure_mapping

logger = get_logger(__name__)
router = APIRouter()


def _isotime(dt: Any) -> str:
    """Safely convert datetime to ISO string."""
    if hasattr(dt, "isoformat"):
        return dt.isoformat() + "Z"
    return str(dt)


def _get_repos() -> tuple[
    SqliteSummaryRepositoryAdapter,
    SqliteRequestRepositoryAdapter,
    SqliteCrawlResultRepositoryAdapter,
    SqliteLLMRepositoryAdapter,
]:
    """Get repository adapters."""
    return (
        SqliteSummaryRepositoryAdapter(database_proxy),
        SqliteRequestRepositoryAdapter(database_proxy),
        SqliteCrawlResultRepositoryAdapter(database_proxy),
        SqliteLLMRepositoryAdapter(database_proxy),
    )


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
    summaries, total, unread_count = await SummaryService.get_user_summaries(
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

    # Build response from dictionary data
    summary_list: list[SummaryCompact] = []
    for summary_dict in summaries:
        # Extract request data from the joined dict
        request_data = summary_dict.get("request") or {}
        if isinstance(request_data, int):
            # If request is just an ID, we need to get request data separately
            request_id = request_data
            input_url = ""
            normalized_url = ""
        else:
            request_id = request_data.get("id", summary_dict.get("request_id"))
            input_url = request_data.get("input_url", "")
            normalized_url = request_data.get("normalized_url", "")

        json_payload = ensure_mapping(summary_dict.get("json_payload"))
        metadata = ensure_mapping(json_payload.get("metadata"))

        summary_list.append(
            SummaryCompact(
                id=summary_dict.get("id"),
                request_id=request_id,
                title=metadata.get("title", "Untitled"),
                domain=metadata.get("domain", ""),
                url=input_url or normalized_url or "",
                tldr=json_payload.get("tldr", ""),
                summary_250=json_payload.get("summary_250", ""),
                reading_time_min=json_payload.get("estimated_reading_time_min", 0),
                topic_tags=json_payload.get("topic_tags", []),
                is_read=summary_dict.get("is_read", False),
                is_favorited=summary_dict.get("is_favorited", False),
                lang=summary_dict.get("lang") or "auto",
                created_at=_isotime(summary_dict.get("created_at")),
                confidence=json_payload.get("confidence", 0.0),
                hallucination_risk=json_payload.get("hallucination_risk", "unknown"),
                image_url=metadata.get("image")
                or metadata.get("og:image")
                or metadata.get("ogImage"),
            )
        )

    pagination = PaginationInfo(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return success_response(
        SummaryListResponse(
            summaries=summary_list,
            pagination=pagination,
            stats=SummaryListStats(total_summaries=total, unread_count=unread_count),
        ),
        pagination=pagination,
    )


@router.get("/by-url")
async def get_summary_by_url(
    url: str = Query(..., description="Original URL of the article"),
    user=Depends(get_current_user),
):
    """Get a single summary (article) by its original URL."""
    summary_repo, request_repo, _, _ = _get_repos()

    # Find request ID by URL (with summary join)
    request_id = await request_repo.async_get_request_id_by_url_with_summary(
        user_id=user["user_id"], url=url
    )

    if not request_id:
        raise ResourceNotFoundError("Article", url)

    # Get summary ID by request ID
    summary_id = await summary_repo.async_get_summary_id_by_request(request_id)
    if not summary_id:
        raise ResourceNotFoundError("Summary", f"request:{request_id}")

    return await get_summary(summary_id=summary_id, user=user)


@router.get("/{summary_id}")
async def get_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Get a single summary with full details."""
    _, request_repo, crawl_repo, llm_repo = _get_repos()

    # Use service layer - it handles authorization and returns summary dict
    summary = await SummaryService.get_summary_by_id(user["user_id"], summary_id)

    # Extract request data from the summary dict
    request_data = summary.get("request") or {}
    if isinstance(request_data, int):
        # If request is just an ID, fetch the full request data
        request_id = request_data
        request_data = await request_repo.async_get_request_by_id(request_id) or {}
    else:
        request_id = request_data.get("id", summary.get("request_id"))

    # Load crawl result and LLM calls via repositories
    crawl_result = await crawl_repo.async_get_crawl_result_by_request(request_id)
    llm_calls = await llm_repo.async_get_llm_calls_by_request(request_id)

    # Build source metadata
    source = {}
    if crawl_result:
        metadata = crawl_result.get("metadata_json") or {}
        source = {
            "url": crawl_result.get("source_url"),
            "title": metadata.get("title"),
            "domain": metadata.get("domain"),
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "http_status": crawl_result.get("http_status"),
            "image_url": metadata.get("image")
            or metadata.get("og:image")
            or metadata.get("ogImage"),
        }

    # Build processing info
    processing = {}
    if llm_calls:
        latest_call = llm_calls[-1]
        processing = {
            "model": latest_call.get("model"),
            "tokens_used": (latest_call.get("tokens_prompt") or 0)
            + (latest_call.get("tokens_completion") or 0),
            "cost_usd": latest_call.get("cost_usd"),
            "latency_ms": sum(call.get("latency_ms") or 0 for call in llm_calls),
            "crawl_latency_ms": crawl_result.get("latency_ms") if crawl_result else None,
            "llm_latency_ms": latest_call.get("latency_ms"),
        }

    # Build SummaryDetailSummary from json_payload
    json_payload = ensure_mapping(summary.get("json_payload"))
    entities_raw = ensure_mapping(json_payload.get("entities"))
    readability_raw = ensure_mapping(json_payload.get("readability"))

    summary_detail = {
        "summary_250": json_payload.get("summary_250", ""),
        "summary_1000": json_payload.get("summary_1000", ""),
        "tldr": json_payload.get("tldr", ""),
        "key_ideas": json_payload.get("key_ideas", []),
        "topic_tags": json_payload.get("topic_tags", []),
        "entities": {
            "people": entities_raw.get("people", []),
            "organizations": entities_raw.get("organizations", []),
            "locations": entities_raw.get("locations", []),
        },
        "estimated_reading_time_min": json_payload.get("estimated_reading_time_min", 0),
        "key_stats": json_payload.get("key_stats", []),
        "answered_questions": json_payload.get("answered_questions", []),
        "readability": (
            {
                "method": readability_raw.get("method", ""),
                "score": readability_raw.get("score", 0.0),
                "level": readability_raw.get("level", ""),
            }
            if readability_raw
            else None
        ),
        "seo_keywords": json_payload.get("seo_keywords", []),
    }

    request_detail = {
        "id": str(request_data.get("id", "")),
        "type": request_data.get("type", ""),
        "url": request_data.get("input_url"),
        "normalized_url": request_data.get("normalized_url"),
        "dedupe_hash": request_data.get("dedupe_hash"),
        "status": request_data.get("status", ""),
        "lang_detected": request_data.get("lang_detected"),
        "created_at": _isotime(request_data.get("created_at")),
        "updated_at": _isotime(request_data.get("updated_at") or request_data.get("created_at")),
    }

    source_detail = {
        "url": source.get("url"),
        "title": source.get("title"),
        "domain": source.get("domain"),
        "author": source.get("author"),
        "published_at": source.get("published_at"),
        "word_count": source.get("word_count"),
        "content_type": source.get("content_type"),
    }

    processing_detail = {
        "model_used": processing.get("model"),
        "tokens_used": processing.get("tokens_used"),
        "processing_time_ms": processing.get("latency_ms"),
        "crawl_time_ms": processing.get("crawl_latency_ms"),
        "confidence": json_payload.get("confidence"),
        "hallucination_risk": json_payload.get("hallucination_risk"),
    }

    return success_response(
        SummaryDetail(
            summary=SummaryDetailSummary(**summary_detail),
            request=SummaryDetailRequest(**request_detail),
            source=SummaryDetailSource(**source_detail),
            processing=SummaryDetailProcessing(**processing_detail),
        )
    )


@router.get("/{summary_id}/content")
async def get_summary_content(
    summary_id: int,
    format: str = Query("markdown", pattern="^(markdown|text)$"),
    user=Depends(get_current_user),
):
    """Get full article content for offline reading."""
    _, request_repo, crawl_repo, _ = _get_repos()

    summary = await SummaryService.get_summary_by_id(user["user_id"], summary_id)

    # Extract request data
    request_data = summary.get("request") or {}
    if isinstance(request_data, int):
        request_id = request_data
        request_data = await request_repo.async_get_request_by_id(request_id) or {}
    else:
        request_id = request_data.get("id", summary.get("request_id"))

    crawl_result = await crawl_repo.async_get_crawl_result_by_request(request_id)

    if not crawl_result:
        raise ResourceNotFoundError("Content", summary_id)

    metadata = ensure_mapping(crawl_result.get("metadata_json"))
    summary_metadata = ensure_mapping(ensure_mapping(summary.get("json_payload")).get("metadata"))
    source_url = (
        crawl_result.get("source_url")
        or request_data.get("input_url")
        or request_data.get("normalized_url")
    )
    title = metadata.get("title") or summary_metadata.get("title")
    domain = metadata.get("domain") or summary_metadata.get("domain")

    content_source = None
    source_format = None
    content_type = None

    if crawl_result.get("content_markdown"):
        content_source = crawl_result.get("content_markdown")
        source_format = "markdown"
        content_type = "text/markdown"
    elif crawl_result.get("content_html"):
        content_source = crawl_result.get("content_html")
        source_format = "html"
        content_type = "text/html"
    elif request_data.get("content_text"):
        content_source = request_data.get("content_text")
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
        crawl_result.get("updated_at") or crawl_result.get("created_at") or datetime.now(UTC)
    )

    return success_response(
        SummaryContentData(
            content=SummaryContent(
                summary_id=summary.get("id"),
                request_id=request_id,
                format=cast('Literal["markdown", "text", "html"]', output_format),
                content=content_value,
                content_type=cast(
                    'Literal["text/markdown", "text/plain", "text/html"]', content_mime
                ),
                lang=summary.get("lang"),
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
    await SummaryService.update_summary(
        user_id=user["user_id"],
        summary_id=summary_id,
        is_read=update.is_read,
    )

    return success_response(
        UpdateSummaryResponse(
            id=summary_id,
            is_read=update.is_read,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    )


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Delete a summary (soft delete)."""
    # Use service layer
    await SummaryService.delete_summary(user_id=user["user_id"], summary_id=summary_id)

    return success_response(
        DeleteSummaryResponse(
            id=summary_id,
            deleted_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    )


@router.post("/{summary_id}/favorite")
async def toggle_favorite(
    summary_id: int,
    user=Depends(get_current_user),
):
    """Toggle the favorite status of a summary."""
    is_favorited = await SummaryService.toggle_favorite(
        user_id=user["user_id"], summary_id=summary_id
    )
    return success_response(ToggleFavoriteResponse(success=True, is_favorited=is_favorited))
