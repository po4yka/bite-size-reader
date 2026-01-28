"""Search and discovery endpoints."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.search_resources import get_chroma_search_service
from app.api.exceptions import ProcessingError
from app.api.models.responses import (
    PaginationInfo,
    SearchResult,
    SearchResultsData,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.core.logging_utils import get_logger
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)
from app.services.chroma_vector_search_service import ChromaVectorSearchService
from app.services.topic_search_utils import ensure_mapping
from app.services.trending_cache import get_trending_payload

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
        topic_search_repo = SqliteTopicSearchRepositoryAdapter(database_proxy)
        request_repo = SqliteRequestRepositoryAdapter(database_proxy)
        summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

        # FTS5 search with pagination
        search_results, total = await topic_search_repo.async_fts_search_paginated(
            q, limit=limit, offset=offset
        )
        request_ids = [r["request_id"] for r in search_results]

        # Batch load requests with user authorization
        requests_map = await request_repo.async_get_requests_by_ids(
            request_ids, user_id=user["user_id"]
        )

        # Batch load summaries for authorized requests
        authorized_request_ids = list(requests_map.keys())
        summaries_map = await summary_repo.async_get_summaries_by_request_ids(
            authorized_request_ids
        )

        results = []
        for idx, search_result in enumerate(search_results):
            req_id = search_result["request_id"]
            request = requests_map.get(req_id)
            if not request:
                continue

            summary = summaries_map.get(req_id)
            if not summary:
                continue

            json_payload = ensure_mapping(summary.get("json_payload"))
            metadata = ensure_mapping(json_payload.get("metadata"))

            results.append(
                {
                    "request_id": req_id,
                    "summary_id": summary.get("id"),
                    "url": request.get("input_url") or request.get("normalized_url"),
                    "title": search_result.get("title") or metadata.get("title", "Untitled"),
                    "domain": search_result.get("source") or metadata.get("domain", ""),
                    "snippet": search_result.get("snippet") or json_payload.get("summary_250", ""),
                    "tldr": json_payload.get("tldr", ""),
                    "published_at": search_result.get("published_at")
                    or metadata.get("published_at"),
                    "created_at": _isotime(request.get("created_at")),
                    "relevance_score": 0.95 - (idx * 0.01),
                    "topic_tags": json_payload.get("topic_tags", []),
                    "is_read": summary.get("is_read", False),
                }
            )

        result_models = [
            SearchResult(
                request_id=item["request_id"],
                summary_id=item["summary_id"],
                url=item["url"],
                title=item["title"],
                domain=item["domain"],
                snippet=item["snippet"],
                tldr=item["tldr"],
                published_at=item["published_at"],
                created_at=item["created_at"],
                relevance_score=item["relevance_score"],
                topic_tags=item["topic_tags"],
                is_read=item["is_read"],
            )
            for item in results
        ]

        pagination = PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )

        return success_response(
            SearchResultsData(
                results=result_models,
                pagination=pagination,
                query=q,
            ),
            pagination=pagination,
        )

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise ProcessingError(f"Search failed: {e!s}") from e


@router.get("/search/semantic")
async def semantic_search_summaries(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    language: str | None = Query(None, min_length=2, max_length=10),
    tags: list[str] | None = Query(None),
    user_scope: str | None = Query(None, min_length=1, max_length=50),
    user=Depends(get_current_user),
    chroma_service: ChromaVectorSearchService = Depends(get_chroma_search_service),
):
    """Semantic search across summaries using Chroma embeddings."""
    try:
        request_repo = SqliteRequestRepositoryAdapter(database_proxy)
        summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

        search_results = await chroma_service.search(
            q,
            language=language,
            tags=tags,
            user_scope=user_scope,
            limit=limit,
            offset=offset,
        )

        request_ids = [result.request_id for result in search_results.results]

        # Batch load requests with user authorization
        requests_map = await request_repo.async_get_requests_by_ids(
            request_ids, user_id=user["user_id"]
        )

        # Batch load summaries
        authorized_request_ids = list(requests_map.keys())
        summaries_map = await summary_repo.async_get_summaries_by_request_ids(
            authorized_request_ids
        )

        results: list[dict[str, object]] = []
        for result in search_results.results:
            request = requests_map.get(result.request_id)
            if not request:
                continue

            summary = summaries_map.get(result.request_id)
            if not summary:
                continue

            json_payload = ensure_mapping(summary.get("json_payload"))
            metadata = ensure_mapping(json_payload.get("metadata"))

            snippet = result.snippet or json_payload.get("summary_250") or json_payload.get("tldr")

            results.append(
                {
                    "request_id": result.request_id,
                    "summary_id": summary.get("id"),
                    "url": result.url or request.get("input_url") or request.get("normalized_url"),
                    "title": result.title or metadata.get("title", "Untitled"),
                    "domain": metadata.get("domain") or metadata.get("source", ""),
                    "snippet": snippet,
                    "tldr": json_payload.get("tldr", ""),
                    "published_at": metadata.get("published_at") or metadata.get("published"),
                    "created_at": _isotime(request.get("created_at")),
                    "relevance_score": result.similarity_score,
                    "topic_tags": json_payload.get("topic_tags") or result.tags,
                    "is_read": summary.get("is_read", False),
                }
            )

        estimated_total = offset + len(results) + (1 if search_results.has_more else 0)

        result_models = [
            SearchResult(
                request_id=item["request_id"],
                summary_id=item["summary_id"],
                url=item["url"],
                title=item["title"],
                domain=item["domain"],
                snippet=item["snippet"],
                tldr=item["tldr"],
                published_at=item["published_at"],
                created_at=item["created_at"],
                relevance_score=item["relevance_score"],
                topic_tags=item["topic_tags"],
                is_read=item["is_read"],
            )
            for item in results
        ]

        pagination = PaginationInfo(
            total=estimated_total,
            limit=limit,
            offset=offset,
            has_more=search_results.has_more,
        )

        return success_response(
            SearchResultsData(
                results=result_models,
                pagination=pagination,
                query=q,
            ),
            pagination=pagination,
        )

    except Exception as e:
        logger.error(f"Semantic search failed: {e}", exc_info=True)
        raise ProcessingError(f"Semantic search failed: {e!s}") from e


@router.get("/topics/trending")
async def get_trending_topics(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Get trending topic tags across recent summaries."""
    payload = await get_trending_payload(user["user_id"], limit=limit, days=days)
    pagination = {
        "total": payload.get("total", limit),
        "limit": limit,
        "offset": 0,
        "has_more": False,
    }
    return success_response(payload, pagination=pagination)


@router.get("/topics/related")
async def get_related_summaries(
    tag: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    """Get summaries related to a specific topic tag."""
    if not tag.startswith("#"):
        tag = f"#{tag}"

    summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

    # Get user summaries with pagination
    summaries_list, _, _ = await summary_repo.async_get_user_summaries(
        user_id=user["user_id"],
        limit=limit,
        offset=offset,
    )

    matching_summaries = []
    for summary in summaries_list:
        json_payload = ensure_mapping(summary.get("json_payload"))
        topic_tags = json_payload.get("topic_tags", [])
        if not isinstance(topic_tags, list):
            topic_tags = []

        if tag.lower() in [t.lower() for t in topic_tags if isinstance(t, str)]:
            metadata = ensure_mapping(json_payload.get("metadata"))
            matching_summaries.append(
                {
                    "summary_id": summary.get("id"),
                    "title": metadata.get("title", "Untitled"),
                    "tldr": json_payload.get("tldr", ""),
                    "created_at": _isotime(summary.get("created_at")),
                }
            )

    pagination = {
        "total": len(matching_summaries),
        "limit": limit,
        "offset": offset,
        "has_more": len(matching_summaries) >= limit,
    }
    return success_response(
        {
            "tag": tag,
            "summaries": matching_summaries,
            "pagination": pagination,
        },
        pagination=pagination,
    )


@router.get("/urls/check-duplicate")
async def check_duplicate(
    url: str = Query(..., min_length=10),
    include_summary: bool = Query(False),
    user=Depends(get_current_user),
):
    """Check if a URL has already been summarized."""
    from app.core.url_utils import compute_dedupe_hash, normalize_url

    request_repo = SqliteRequestRepositoryAdapter(database_proxy)
    summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

    normalized = normalize_url(url)
    dedupe_hash = compute_dedupe_hash(normalized)

    existing = await request_repo.async_get_request_by_dedupe_hash(dedupe_hash)

    if not existing or existing.get("user_id") != user["user_id"]:
        return success_response(
            {
                "is_duplicate": False,
                "normalized_url": normalized,
                "dedupe_hash": dedupe_hash,
            }
        )

    summary = await summary_repo.async_get_summary_by_request(existing["id"])

    response_data = {
        "is_duplicate": True,
        "request_id": existing["id"],
        "summary_id": summary["id"] if summary else None,
        "summarized_at": _isotime(existing.get("created_at")),
    }

    if include_summary and summary:
        json_payload = ensure_mapping(summary.get("json_payload"))
        metadata = ensure_mapping(json_payload.get("metadata"))

        response_data["summary"] = {
            "title": metadata.get("title", "Untitled"),
            "tldr": json_payload.get("tldr", ""),
            "url": existing.get("input_url") or existing.get("normalized_url"),
        }

    return success_response(response_data)


def _isotime(dt_val) -> str:
    """Convert datetime to ISO string with Z suffix."""
    if dt_val is None:
        return ""
    if hasattr(dt_val, "isoformat"):
        return dt_val.isoformat() + "Z"
    return str(dt_val)
