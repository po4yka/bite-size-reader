"""Search and discovery endpoints."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.database import (
    get_request_repository,
    get_summary_repository,
    get_topic_search_repository,
    resolve_repository_session,
)
from app.api.dependencies.search_resources import get_chroma_search_service
from app.api.exceptions import ProcessingError
from app.api.models.responses import PaginationInfo, SearchResultsData, success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import SearchFilters, build_facets, infer_intent, isotime, resolve_mode
from app.api.search_insights import compute_search_insights_payload
from app.api.search_ranking import (
    build_fts_hits,
    build_ranked_search_rows,
    build_semantic_filtered_rows,
    build_semantic_hits,
    candidate_request_ids,
    rows_to_search_results,
)
from app.application.services.topic_search_utils import ensure_mapping
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.infrastructure.cache.trending_cache import get_trending_payload

logger = get_logger(__name__)
router = APIRouter()
SqliteTopicSearchRepositoryAdapter = get_topic_search_repository
SqliteRequestRepositoryAdapter = get_request_repository
SqliteSummaryRepositoryAdapter = get_summary_repository
__all__ = [
    "SqliteRequestRepositoryAdapter",
    "SqliteSummaryRepositoryAdapter",
    "SqliteTopicSearchRepositoryAdapter",
    "router",
]


def _instantiate_repository(factory: Any) -> Any:
    session = resolve_repository_session()
    try:
        return factory(session)
    except TypeError:
        return factory()


def _build_search_repositories() -> tuple[Any, Any, Any]:
    return (
        _instantiate_repository(SqliteTopicSearchRepositoryAdapter),
        _instantiate_repository(SqliteRequestRepositoryAdapter),
        _instantiate_repository(SqliteSummaryRepositoryAdapter),
    )


def _search_filter_params(
    language: str | None = Query(None, min_length=2, max_length=10),
    tags: list[str] | None = Query(None),
    domains: list[str] | None = Query(None),
    start_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    is_read: bool | None = Query(None),
    is_favorited: bool | None = Query(None),
) -> SearchFilters:
    return SearchFilters(
        language=language,
        tags=tags,
        domains=domains,
        start_date=start_date,
        end_date=end_date,
        is_read=is_read,
        is_favorited=is_favorited,
    )


@router.get("/search")
async def search_summaries(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mode: str = Query("auto", pattern="^(auto|keyword|semantic|hybrid)$"),
    min_similarity: float = Query(0.2, ge=0.0, le=1.0),
    filters: SearchFilters = Depends(_search_filter_params),
    user: dict[str, Any] = Depends(get_current_user),
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
        topic_search_repo, request_repo, summary_repo = _build_search_repositories()
        intent = infer_intent(q)
        resolved_mode = resolve_mode(mode, intent)
        fetch_limit = min(300, max(limit * 4, limit + 25))
        fts_query = re.sub(r"#", " ", q).strip() or q
        fts_results, _ = await topic_search_repo.async_fts_search_paginated(
            fts_query,
            limit=fetch_limit,
            offset=0,
            user_id=user["user_id"],
        )
        fts_by_request_id = build_fts_hits(fts_results)
        semantic_by_request_id = await build_semantic_hits(
            q=q,
            resolved_mode=resolved_mode,
            filters=filters,
            user_id=user["user_id"],
            fetch_limit=fetch_limit,
            min_similarity=min_similarity,
            get_chroma_service=get_chroma_search_service,
        )
        request_ids = candidate_request_ids(
            resolved_mode,
            fts_by_request_id,
            semantic_by_request_id,
        )
        requests_map = await request_repo.async_get_requests_by_ids(
            request_ids,
            user_id=user["user_id"],
        )
        summaries_map = await summary_repo.async_get_summaries_by_request_ids(
            list(requests_map.keys())
        )
        ranked_rows = build_ranked_search_rows(
            q=q,
            resolved_mode=resolved_mode,
            candidate_request_ids=request_ids,
            requests_map=requests_map,
            summaries_map=summaries_map,
            fts_by_request_id=fts_by_request_id,
            semantic_by_request_id=semantic_by_request_id,
            filters=filters,
        )
        facets = build_facets(ranked_rows)
        paged_rows = ranked_rows[offset : offset + limit]
        result_models = rows_to_search_results(paged_rows)
        pagination = PaginationInfo(
            total=len(ranked_rows),
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < len(ranked_rows),
        )
        return success_response(
            SearchResultsData(
                results=result_models,
                pagination=pagination,
                query=q,
                intent=intent,
                mode=resolved_mode,
                facets=facets,
            ),
            pagination=pagination,
        )
    except Exception as exc:
        logger.error("Search failed: %s", exc, exc_info=True)
        raise ProcessingError(f"Search failed: {exc!s}") from exc


@router.get("/search/semantic")
async def semantic_search_summaries(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_scope: str | None = Query(None, min_length=1, max_length=50),
    min_similarity: float = Query(0.2, ge=0.0, le=1.0),
    filters: SearchFilters = Depends(_search_filter_params),
    user: dict[str, Any] = Depends(get_current_user),
    chroma_service: Any = Depends(get_chroma_search_service),
):
    """Semantic search across summaries using Chroma embeddings."""
    try:
        _, request_repo, summary_repo = _build_search_repositories()
        search_results = await chroma_service.search(
            q,
            language=filters.language,
            tags=filters.tags,
            user_scope=user_scope,
            user_id=user["user_id"],
            limit=limit,
            offset=offset,
        )
        request_ids = [result.request_id for result in search_results.results]
        requests_map = await request_repo.async_get_requests_by_ids(
            request_ids,
            user_id=user["user_id"],
        )
        summaries_map = await summary_repo.async_get_summaries_by_request_ids(
            list(requests_map.keys())
        )
        filtered_rows = build_semantic_filtered_rows(
            q=q,
            min_similarity=min_similarity,
            filters=filters,
            search_results=search_results,
            requests_map=requests_map,
            summaries_map=summaries_map,
        )
        facets = build_facets(filtered_rows)
        paged_rows = filtered_rows[offset : offset + limit]
        result_models = rows_to_search_results(paged_rows)
        estimated_total = len(filtered_rows) + (1 if search_results.has_more else 0)
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
                intent=infer_intent(q),
                mode="semantic",
                facets=facets,
            ),
            pagination=pagination,
        )
    except Exception as exc:
        logger.error("Semantic search failed: %s", exc, exc_info=True)
        raise ProcessingError(f"Semantic search failed: {exc!s}") from exc


@router.get("/topics/trending")
async def get_trending_topics(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    user: dict[str, Any] = Depends(get_current_user),
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


@router.get("/search/insights")
async def get_search_insights(
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(20, ge=5, le=100),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Search analytics snapshot: trends, entities, diversity, mix and coverage gaps."""
    _, _, summary_repo = _build_search_repositories()
    now = datetime.now(UTC)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    rows = await summary_repo.async_get_user_summaries_for_insights(
        user_id=user["user_id"],
        request_created_after=previous_start,
        limit=max(limit * 60, 1200),
    )
    payload = await asyncio.to_thread(
        compute_search_insights_payload,
        rows=rows,
        now=now,
        current_start=current_start,
        previous_start=previous_start,
        days=days,
        limit=limit,
    )
    pagination = {
        "total": len(payload.get("topic_trends", [])),
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
    user: dict[str, Any] = Depends(get_current_user),
):
    """Get summaries related to a specific topic tag."""
    _, _, summary_repo = _build_search_repositories()
    if not tag.startswith("#"):
        tag = f"#{tag}"

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
                    "created_at": isotime(summary.get("created_at")),
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
    user: dict[str, Any] = Depends(get_current_user),
):
    """Check if a URL has already been summarized."""
    from app.core.url_utils import compute_dedupe_hash, normalize_url

    _, request_repo, summary_repo = _build_search_repositories()
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
        "summarized_at": isotime(existing.get("created_at")),
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
