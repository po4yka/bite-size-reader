"""Search and discovery endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.database import get_search_read_model_use_case
from app.api.exceptions import ProcessingError
from app.api.models.responses import success_response
from app.api.routers.auth import get_current_user
from app.api.search_helpers import SearchFilters
from app.api.services.search_service import SearchService
from app.core.logging_utils import get_logger
from app.infrastructure.cache.trending_cache import get_trending_payload

if TYPE_CHECKING:
    from app.application.use_cases.search_read_model import SearchReadModelUseCase

logger = get_logger(__name__)
router = APIRouter()


def _get_search_service(request: Request) -> SearchService:
    """Resolve the search orchestration service from shared dependencies."""
    read_model: SearchReadModelUseCase = get_search_read_model_use_case(request=request)
    return SearchService(search_read_model=read_model)


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
    search_service: SearchService = Depends(_get_search_service),
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
        result = await search_service.search_summaries(
            q=q,
            user_id=user["user_id"],
            limit=limit,
            offset=offset,
            mode=mode,
            min_similarity=min_similarity,
            filters=filters,
        )
        return success_response(
            result,
            pagination=result.pagination,
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
    search_service: SearchService = Depends(_get_search_service),
):
    """Semantic search across summaries using Qdrant embeddings."""
    try:
        result = await search_service.semantic_search_summaries(
            q=q,
            user_id=user["user_id"],
            limit=limit,
            offset=offset,
            user_scope=user_scope,
            min_similarity=min_similarity,
            filters=filters,
        )
        return success_response(
            result,
            pagination=result.pagination,
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
    search_service: SearchService = Depends(_get_search_service),
):
    """Search analytics snapshot: trends, entities, diversity, mix and coverage gaps."""
    payload, pagination = await search_service.get_search_insights(
        user_id=user["user_id"],
        days=days,
        limit=limit,
    )
    return success_response(payload, pagination=pagination)


@router.get("/topics/related")
async def get_related_summaries(
    tag: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
    search_service: SearchService = Depends(_get_search_service),
):
    """Get summaries related to a specific topic tag."""
    payload = await search_service.get_related_summaries(
        user_id=user["user_id"],
        tag=tag,
        limit=limit,
        offset=offset,
    )
    return success_response(payload, pagination=payload["pagination"])


@router.get("/urls/check-duplicate")
async def check_duplicate(
    url: str = Query(..., min_length=10),
    include_summary: bool = Query(False),
    user: dict[str, Any] = Depends(get_current_user),
    search_service: SearchService = Depends(_get_search_service),
):
    """Check if a URL has already been summarized."""
    payload = await search_service.check_duplicate(
        user_id=user["user_id"],
        url=url,
        include_summary=include_summary,
    )
    return success_response(payload)
