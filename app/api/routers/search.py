"""Search and discovery endpoints."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.search_resources import get_chroma_search_service
from app.api.exceptions import ProcessingError
from app.api.models.responses import SearchResult, SearchResultsData, success_response
from app.api.routers.auth import get_current_user
from app.core.logging_utils import get_logger
from app.db.models import Request as RequestModel, Summary, TopicSearchIndex
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
        # FTS5 search query
        search_query = (
            TopicSearchIndex.search(q).order_by(TopicSearchIndex.rank).limit(limit).offset(offset)
        )

        # Execute query once and get request IDs
        search_results = list(search_query)
        request_ids = [result.request_id for result in search_results]

        # Batch load all requests and summaries in 2 queries (fixes N+1)
        # Query 1: Load all requests with user authorization
        requests_query = RequestModel.select().where(
            (RequestModel.id.in_(request_ids)) & (RequestModel.user_id == user["user_id"])
        )
        requests_map = {req.id: req for req in requests_query}

        # Query 2: Load all summaries for authorized requests
        summaries_query = Summary.select().where(Summary.request.in_(list(requests_map.keys())))
        summaries_map = {summ.request.id: summ for summ in summaries_query}

        results = []
        for idx, result in enumerate(search_results):
            # Get pre-loaded request (no additional query)
            request = requests_map.get(result.request_id)
            if not request:
                # User doesn't have access to this result, skip it
                continue

            # Get pre-loaded summary (no additional query)
            summary = summaries_map.get(request.id)
            if not summary:
                continue

            json_payload = ensure_mapping(summary.json_payload)
            metadata = ensure_mapping(json_payload.get("metadata"))

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

        pagination = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

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
        search_results = await chroma_service.search(
            q,
            language=language,
            tags=tags,
            user_scope=user_scope,
            limit=limit,
            offset=offset,
        )

        request_ids = [result.request_id for result in search_results.results]

        requests_query = RequestModel.select().where(
            (RequestModel.id.in_(request_ids)) & (RequestModel.user_id == user["user_id"])
        )
        requests_map = {req.id: req for req in requests_query}

        summaries_query = Summary.select().where(Summary.request.in_(list(requests_map.keys())))
        summaries_map = {summ.request.id: summ for summ in summaries_query}

        results: list[dict[str, object]] = []

        for result in search_results.results:
            request = requests_map.get(result.request_id)
            if not request:
                continue

            summary = summaries_map.get(request.id)
            if not summary:
                continue

            json_payload = ensure_mapping(summary.json_payload)
            metadata = ensure_mapping(json_payload.get("metadata"))

            snippet = result.snippet or json_payload.get("summary_250") or json_payload.get("tldr")

            results.append(
                {
                    "request_id": request.id,
                    "summary_id": summary.id,
                    "url": result.url or request.input_url or request.normalized_url,
                    "title": result.title or metadata.get("title", "Untitled"),
                    "domain": metadata.get("domain") or metadata.get("source", ""),
                    "snippet": snippet,
                    "tldr": json_payload.get("tldr", ""),
                    "published_at": metadata.get("published_at") or metadata.get("published"),
                    "created_at": request.created_at.isoformat() + "Z",
                    "relevance_score": result.similarity_score,
                    "topic_tags": json_payload.get("topic_tags") or result.tags,
                    "is_read": summary.is_read,
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

        pagination = {
            "total": estimated_total,
            "limit": limit,
            "offset": offset,
            "has_more": search_results.has_more,
        }

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
    # Normalize tag (add # if missing)
    if not tag.startswith("#"):
        tag = f"#{tag}"

    # Query summaries with this tag with user authorization
    # Note: This iterates through all summaries to check JSON payload.
    # For better performance with large datasets, consider:
    # - FTS5 index on topic_tags
    # - JSON extraction in SQLite (JSON_EXTRACT with index)
    # - Denormalized topic_tags table with foreign keys
    summaries = (
        Summary.select()
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])  # Only user's summaries
        .limit(limit)
        .offset(offset)
    )

    matching_summaries = []
    for summary in summaries:
        json_payload = ensure_mapping(summary.json_payload)
        topic_tags = json_payload.get("topic_tags", [])
        if not isinstance(topic_tags, list):
            topic_tags = []

        if tag.lower() in [t.lower() for t in topic_tags if isinstance(t, str)]:
            metadata = ensure_mapping(json_payload.get("metadata"))
            matching_summaries.append(
                {
                    "summary_id": summary.id,
                    "title": metadata.get("title", "Untitled"),
                    "tldr": json_payload.get("tldr", ""),
                    "created_at": summary.created_at.isoformat() + "Z",
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

    normalized = normalize_url(url)
    dedupe_hash = compute_dedupe_hash(normalized)

    # Check for existing request with user authorization
    existing = (
        RequestModel.select()
        .where(
            (RequestModel.dedupe_hash == dedupe_hash) & (RequestModel.user_id == user["user_id"])
        )
        .first()
    )

    if not existing:
        return success_response(
            {
                "is_duplicate": False,
                "normalized_url": normalized,
                "dedupe_hash": dedupe_hash,
            }
        )

    # Found duplicate - load summary in same query to avoid N+1
    summary = Summary.select().where(Summary.request == existing.id).first()

    response_data = {
        "is_duplicate": True,
        "request_id": existing.id,
        "summary_id": summary.id if summary else None,
        "summarized_at": existing.created_at.isoformat() + "Z",
    }

    if include_summary and summary:
        json_payload = ensure_mapping(summary.json_payload)
        metadata = ensure_mapping(json_payload.get("metadata"))

        response_data["summary"] = {
            "title": metadata.get("title", "Untitled"),
            "tldr": json_payload.get("tldr", ""),
            "url": existing.input_url or existing.normalized_url,
        }

    return success_response(response_data)
