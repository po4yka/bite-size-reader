"""
Search and discovery endpoints.
"""

from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.auth import get_current_user
from app.db.models import TopicSearchIndex, Summary, Request as RequestModel
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/search")
async def search_summaries(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    """
    Full-text search across all summaries using FTS5.

    Search Syntax:
    - Wildcard: bitcoin*
    - Phrase: "artificial intelligence"
    - Boolean: blockchain AND crypto
    - Exclusion: crypto NOT bitcoin
    """
    try:
        # FTS5 search query
        search_query = (
            TopicSearchIndex.search(q)
            .order_by(TopicSearchIndex.rank)
            .limit(limit)
            .offset(offset)
        )

        results = []
        for idx, result in enumerate(search_query):
            request = RequestModel.select().where(RequestModel.id == result.request_id).first()

            if not request:
                continue

            summary = Summary.select().where(Summary.request == request).first()

            if not summary:
                continue

            json_payload = summary.json_payload or {}
            metadata = json_payload.get("metadata", {})

            results.append(
                {
                    "request_id": request.id,
                    "summary_id": summary.id,
                    "url": request.input_url or request.normalized_url,
                    "title": result.title or metadata.get("title", "Untitled"),
                    "domain": result.source or metadata.get("domain", ""),
                    "snippet": result.snippet or json_payload.get("summary_250", ""),
                    "tldr": json_payload.get("tldr", ""),
                    "published_at": result.published_at or metadata.get("published_at"),
                    "created_at": request.created_at.isoformat() + "Z",
                    "relevance_score": 0.95 - (idx * 0.01),  # Mock score
                    "topic_tags": json_payload.get("topic_tags", []),
                    "is_read": summary.is_read,
                }
            )

        total = search_query.count()

        return {
            "success": True,
            "data": {
                "results": results,
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total,
                },
                "query": q,
            },
        }

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/topics/trending")
async def get_trending_topics(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Get trending topic tags across recent summaries."""
    # TODO: Implement actual trending calculation
    # For now, return mock data

    return {
        "success": True,
        "data": {
            "tags": [
                {"tag": "#blockchain", "count": 42, "trend": "up", "percentage_change": 15.5},
                {"tag": "#cryptocurrency", "count": 38, "trend": "stable", "percentage_change": 0.2},
                {"tag": "#ai", "count": 35, "trend": "down", "percentage_change": -8.3},
            ],
            "time_range": {
                "start": "2025-10-16T00:00:00Z",
                "end": "2025-11-15T23:59:59Z",
            },
        },
    }


@router.get("/topics/related")
async def get_related_summaries(
    tag: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    """Get summaries related to a specific topic tag."""
    # Normalize tag (add # if missing)
    if not tag.startswith("#"):
        tag = f"#{tag}"

    # Query summaries with this tag
    # TODO: This requires a better query strategy (maybe FTS5 or JSON extraction)
    summaries = Summary.select().join(RequestModel).limit(limit).offset(offset)

    matching_summaries = []
    for summary in summaries:
        json_payload = summary.json_payload or {}
        topic_tags = json_payload.get("topic_tags", [])

        if tag.lower() in [t.lower() for t in topic_tags]:
            metadata = json_payload.get("metadata", {})
            matching_summaries.append(
                {
                    "summary_id": summary.id,
                    "title": metadata.get("title", "Untitled"),
                    "tldr": json_payload.get("tldr", ""),
                    "created_at": summary.created_at.isoformat() + "Z",
                }
            )

    return {
        "success": True,
        "data": {
            "tag": tag,
            "summaries": matching_summaries,
            "pagination": {
                "total": len(matching_summaries),
                "limit": limit,
                "offset": offset,
            },
        },
    }


@router.get("/urls/check-duplicate")
async def check_duplicate(
    url: str = Query(..., min_length=10),
    include_summary: bool = Query(False),
    user=Depends(get_current_user),
):
    """Check if a URL has already been summarized."""
    from app.core.url_utils import normalize_url, compute_dedupe_hash

    normalized = normalize_url(url)
    dedupe_hash = compute_dedupe_hash(normalized)

    # Check for existing request
    existing = RequestModel.select().where(RequestModel.dedupe_hash == dedupe_hash).first()

    if not existing:
        return {
            "success": True,
            "data": {
                "is_duplicate": False,
                "normalized_url": normalized,
                "dedupe_hash": dedupe_hash,
            },
        }

    # Found duplicate
    summary = Summary.select().where(Summary.request == existing).first()

    response_data = {
        "is_duplicate": True,
        "request_id": existing.id,
        "summary_id": summary.id if summary else None,
        "summarized_at": existing.created_at.isoformat() + "Z",
    }

    if include_summary and summary:
        json_payload = summary.json_payload or {}
        metadata = json_payload.get("metadata", {})

        response_data["summary"] = {
            "title": metadata.get("title", "Untitled"),
            "tldr": json_payload.get("tldr", ""),
            "url": existing.input_url or existing.normalized_url,
        }

    return {"success": True, "data": response_data}
