"""Search and discovery endpoints."""

import math
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

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
from app.core.time_utils import UTC
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


_HASHTAG_RE = re.compile(r"#([\w-]{1,50})", re.UNICODE)
_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")


def _query_tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w-]{2,}", text, re.UNICODE)}


def _lexical_overlap(query: str, text: str) -> float:
    query_terms = _query_tokens(query)
    if not query_terms:
        return 0.0
    body_terms = _query_tokens(text)
    if not body_terms:
        return 0.0
    return len(query_terms.intersection(body_terms)) / len(query_terms)


def _extract_query_tags(query: str) -> list[str]:
    tags = [f"#{match.lower()}" for match in _HASHTAG_RE.findall(query)]
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result


def _infer_intent(query: str) -> str:
    lowered = query.strip().lower()
    if lowered.startswith(("similar to ", "like ")):
        return "similarity"
    if lowered.endswith("?") or lowered.startswith(
        ("why ", "how ", "what ", "which ", "who ", "when ")
    ):
        return "question"
    if _HASHTAG_RE.search(lowered):
        return "topic"
    if _ENTITY_RE.search(query):
        return "entity"
    return "keyword"


def _resolve_mode(requested_mode: str, intent: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    if intent in {"question", "similarity", "entity", "topic"}:
        return "hybrid"
    return "keyword"


def _freshness_score(created_at: Any) -> float:
    if not created_at:
        return 0.0
    if isinstance(created_at, str):
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    else:
        created = created_at
    now = datetime.now(created.tzinfo) if getattr(created, "tzinfo", None) else datetime.utcnow()
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    return max(0.0, min(1.0, math.exp(-age_days / 45.0)))


def _popularity_score(summary: dict[str, Any], payload: dict[str, Any]) -> float:
    favorited = 1.0 if summary.get("is_favorited") else 0.0
    key_stats = payload.get("key_stats") or []
    answered = payload.get("answered_questions") or []
    richness = min(1.0, (len(key_stats) + len(answered)) / 12.0)
    return max(0.0, min(1.0, 0.7 * favorited + 0.3 * richness))


def _score_result(
    *,
    mode: str,
    fts_score: float,
    semantic_score: float,
    freshness: float,
    popularity: float,
    lexical: float,
) -> float:
    if mode == "keyword":
        return (0.62 * fts_score) + (0.2 * freshness) + (0.1 * popularity) + (0.08 * lexical)
    if mode == "semantic":
        return (0.65 * semantic_score) + (0.18 * freshness) + (0.09 * popularity) + (0.08 * lexical)
    return (
        (0.35 * fts_score)
        + (0.43 * semantic_score)
        + (0.12 * freshness)
        + (0.06 * popularity)
        + (0.04 * lexical)
    )


def _build_match_explanation(
    *,
    mode: str,
    fts_score: float,
    semantic_score: float,
    freshness: float,
    popularity: float,
) -> tuple[list[str], str]:
    signals: list[str] = []
    if fts_score > 0.25:
        signals.append("keyword_match")
    if semantic_score > 0.35:
        signals.append("semantic_match")
    if freshness > 0.55:
        signals.append("recent")
    if popularity > 0.4:
        signals.append("popular")

    if not signals:
        signals.append("broad_match")

    reason = ", ".join(signals)
    return signals, f"Ranked by {mode} scoring using {reason}."


def _passes_filters(
    *,
    request: dict[str, Any],
    summary: dict[str, Any],
    payload: dict[str, Any],
    lang: str | None,
    tags: list[str] | None,
    domains: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    is_read: bool | None,
    is_favorited: bool | None,
) -> bool:
    if lang and (summary.get("lang") or "").lower() != lang.lower():
        return False
    if is_read is not None and bool(summary.get("is_read")) != bool(is_read):
        return False
    if is_favorited is not None and bool(summary.get("is_favorited")) != bool(is_favorited):
        return False

    metadata = ensure_mapping(payload.get("metadata"))
    domain = str(metadata.get("domain") or "").lower()
    if domains:
        normalized_domains = {str(item).lower() for item in domains if str(item).strip()}
        if normalized_domains and domain not in normalized_domains:
            return False

    topic_tags = payload.get("topic_tags") or []
    tag_set = {str(item).lower() for item in topic_tags if str(item).strip()}
    if tags:
        required = []
        for raw in tags:
            t = str(raw).strip().lower()
            required.append(t if t.startswith("#") else f"#{t}")
        if not set(required).intersection(tag_set):
            return False

    created_at = request.get("created_at")
    if isinstance(created_at, str):
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_dt = None
    else:
        created_dt = created_at

    if created_dt and start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            if created_dt.date() < start_dt.date():
                return False
        except ValueError:
            pass
    if created_dt and end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            if created_dt.date() > end_dt.date():
                return False
        except ValueError:
            pass

    return True


def _build_facets(results: list[dict[str, Any]]) -> dict[str, Any]:
    domains: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    read_states: Counter[str] = Counter()

    for item in results:
        domain = item.get("domain")
        if domain:
            domains[str(domain).lower()] += 1
        lang = item.get("lang")
        if lang:
            languages[str(lang).lower()] += 1
        for tag in item.get("topic_tags", []) or []:
            if tag:
                tags[str(tag).lower()] += 1
        read_states["read" if item.get("is_read") else "unread"] += 1

    def _top(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
        return [{"value": key, "count": count} for key, count in counter.most_common(limit)]

    return {
        "domains": _top(domains),
        "languages": _top(languages),
        "tags": _top(tags),
        "read_states": _top(read_states, limit=4),
    }


def _period_tag_counts(
    rows: list[tuple[datetime, list[str]]], start: datetime, end: datetime
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for created_at, tags in rows:
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        if created_at < start or created_at >= end:
            continue
        for tag in tags:
            normalized = str(tag).strip().lower()
            if normalized:
                counts[normalized] += 1
    return counts


@router.get("/search")
async def search_summaries(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mode: str = Query("auto", pattern="^(auto|keyword|semantic|hybrid)$"),
    language: str | None = Query(None, min_length=2, max_length=10),
    tags: list[str] | None = Query(None),
    domains: list[str] | None = Query(None),
    start_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    is_read: bool | None = Query(None),
    is_favorited: bool | None = Query(None),
    min_similarity: float = Query(0.2, ge=0.0, le=1.0),
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

        intent = _infer_intent(q)
        resolved_mode = _resolve_mode(mode, intent)

        fetch_limit = min(300, max(limit * 4, limit + 25))

        fts_query = re.sub(r"#", " ", q).strip() or q
        fts_results, _ = await topic_search_repo.async_fts_search_paginated(
            fts_query, limit=fetch_limit, offset=0
        )
        fts_by_request_id: dict[int, dict[str, Any]] = {}
        for idx, row in enumerate(fts_results):
            try:
                req_id = int(row["request_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if req_id in fts_by_request_id:
                continue
            fts_by_request_id[req_id] = {
                "position": idx,
                "score": max(0.0, 1.0 - (idx / max(len(fts_results), 1))),
                "row": row,
            }

        semantic_by_request_id: dict[int, dict[str, Any]] = {}
        if resolved_mode in {"semantic", "hybrid"}:
            try:
                chroma_service = await get_chroma_search_service()
            except Exception:
                chroma_service = None
                logger.warning("search_chroma_unavailable", exc_info=True)

            semantic_tags = tags or _extract_query_tags(q) or None
            if chroma_service is not None:
                semantic_results = await chroma_service.search(
                    q,
                    language=language,
                    tags=semantic_tags,
                    user_id=user["user_id"],
                    limit=fetch_limit,
                    offset=0,
                )
                for idx, row in enumerate(semantic_results.results):
                    if row.similarity_score < min_similarity:
                        continue
                    if row.request_id in semantic_by_request_id:
                        continue
                    semantic_by_request_id[row.request_id] = {
                        "position": idx,
                        "score": float(row.similarity_score),
                        "row": row,
                    }

        if resolved_mode == "keyword":
            candidate_request_ids = list(fts_by_request_id.keys())
        elif resolved_mode == "semantic":
            candidate_request_ids = list(semantic_by_request_id.keys())
        else:
            candidate_request_ids = list(
                dict.fromkeys([*fts_by_request_id.keys(), *semantic_by_request_id.keys()])
            )

        requests_map = await request_repo.async_get_requests_by_ids(
            candidate_request_ids, user_id=user["user_id"]
        )
        summaries_map = await summary_repo.async_get_summaries_by_request_ids(
            list(requests_map.keys())
        )

        ranked_rows: list[dict[str, Any]] = []
        for req_id in candidate_request_ids:
            request = requests_map.get(req_id)
            summary = summaries_map.get(req_id)
            if not request or not summary:
                continue

            payload = ensure_mapping(summary.get("json_payload"))
            metadata = ensure_mapping(payload.get("metadata"))

            if not _passes_filters(
                request=request,
                summary=summary,
                payload=payload,
                lang=language,
                tags=tags,
                domains=domains,
                start_date=start_date,
                end_date=end_date,
                is_read=is_read,
                is_favorited=is_favorited,
            ):
                continue

            fts_hit = fts_by_request_id.get(req_id)
            semantic_hit = semantic_by_request_id.get(req_id)
            fts_score = float(fts_hit["score"]) if fts_hit else 0.0
            semantic_score = float(semantic_hit["score"]) if semantic_hit else 0.0
            freshness = _freshness_score(request.get("created_at"))
            popularity = _popularity_score(summary, payload)

            snippet = (
                (
                    semantic_hit["row"].snippet
                    if semantic_hit and semantic_hit["row"].snippet
                    else None
                )
                or (fts_hit["row"].get("snippet") if fts_hit else None)
                or payload.get("summary_250")
                or payload.get("tldr", "")
            )
            lexical = _lexical_overlap(q, f"{metadata.get('title', '')} {snippet or ''}")
            score = _score_result(
                mode=resolved_mode,
                fts_score=fts_score,
                semantic_score=semantic_score,
                freshness=freshness,
                popularity=popularity,
                lexical=lexical,
            )
            signals, reason = _build_match_explanation(
                mode=resolved_mode,
                fts_score=fts_score,
                semantic_score=semantic_score,
                freshness=freshness,
                popularity=popularity,
            )

            ranked_rows.append(
                {
                    "request_id": req_id,
                    "summary_id": summary.get("id"),
                    "url": request.get("input_url") or request.get("normalized_url"),
                    "title": (semantic_hit["row"].title if semantic_hit else None)
                    or (fts_hit["row"].get("title") if fts_hit else None)
                    or metadata.get("title", "Untitled"),
                    "domain": metadata.get("domain")
                    or (fts_hit["row"].get("source") if fts_hit else ""),
                    "snippet": snippet,
                    "tldr": payload.get("tldr", ""),
                    "published_at": metadata.get("published_at")
                    or (fts_hit["row"].get("published_at") if fts_hit else None),
                    "created_at": _isotime(request.get("created_at")),
                    "relevance_score": round(score, 4),
                    "topic_tags": payload.get("topic_tags", []),
                    "is_read": summary.get("is_read", False),
                    "lang": summary.get("lang"),
                    "match_signals": signals,
                    "match_explanation": reason,
                    "score_breakdown": {
                        "fts": round(fts_score, 4),
                        "semantic": round(semantic_score, 4),
                        "freshness": round(freshness, 4),
                        "popularity": round(popularity, 4),
                        "lexical": round(lexical, 4),
                    },
                }
            )

        ranked_rows.sort(key=lambda item: float(item.get("relevance_score", 0.0)), reverse=True)
        facets = _build_facets(ranked_rows)
        paged = ranked_rows[offset : offset + limit]

        result_models = []
        for item in paged:
            result_models.append(
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
                    match_signals=item["match_signals"],
                    match_explanation=item["match_explanation"],
                    score_breakdown=item["score_breakdown"],
                )
            )

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
    domains: list[str] | None = Query(None),
    start_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="ISO date (YYYY-MM-DD)"),
    is_read: bool | None = Query(None),
    is_favorited: bool | None = Query(None),
    user_scope: str | None = Query(None, min_length=1, max_length=50),
    min_similarity: float = Query(0.2, ge=0.0, le=1.0),
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
            user_id=user["user_id"],
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

        filtered_rows: list[dict[str, Any]] = []
        for result in search_results.results:
            request = requests_map.get(result.request_id)
            if not request:
                continue

            summary = summaries_map.get(result.request_id)
            if not summary:
                continue

            json_payload = ensure_mapping(summary.get("json_payload"))
            metadata = ensure_mapping(json_payload.get("metadata"))

            if result.similarity_score < min_similarity:
                continue

            if not _passes_filters(
                request=request,
                summary=summary,
                payload=json_payload,
                lang=language,
                tags=tags,
                domains=domains,
                start_date=start_date,
                end_date=end_date,
                is_read=is_read,
                is_favorited=is_favorited,
            ):
                continue

            snippet = result.snippet or json_payload.get("summary_250") or json_payload.get("tldr")
            freshness = _freshness_score(request.get("created_at"))
            popularity = _popularity_score(summary, json_payload)
            lexical = _lexical_overlap(q, f"{metadata.get('title', '')} {snippet or ''}")
            relevance = _score_result(
                mode="semantic",
                fts_score=0.0,
                semantic_score=float(result.similarity_score),
                freshness=freshness,
                popularity=popularity,
                lexical=lexical,
            )
            signals, reason = _build_match_explanation(
                mode="semantic",
                fts_score=0.0,
                semantic_score=float(result.similarity_score),
                freshness=freshness,
                popularity=popularity,
            )

            filtered_rows.append(
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
                    "relevance_score": round(relevance, 4),
                    "topic_tags": json_payload.get("topic_tags") or result.tags,
                    "is_read": summary.get("is_read", False),
                    "match_signals": signals,
                    "match_explanation": reason,
                    "score_breakdown": {
                        "fts": 0.0,
                        "semantic": round(float(result.similarity_score), 4),
                        "freshness": round(freshness, 4),
                        "popularity": round(popularity, 4),
                        "lexical": round(lexical, 4),
                    },
                    "lang": summary.get("lang"),
                }
            )

        filtered_rows.sort(key=lambda item: float(item.get("relevance_score", 0.0)), reverse=True)
        facets = _build_facets(filtered_rows)
        paged_rows = filtered_rows[offset : offset + limit]
        result_models: list[SearchResult] = []
        for item in paged_rows:
            result_models.append(
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
                    match_signals=item["match_signals"],
                    match_explanation=item["match_explanation"],
                    score_breakdown=item["score_breakdown"],
                )
            )

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
                intent=_infer_intent(q),
                mode="semantic",
                facets=facets,
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


@router.get("/search/insights")
async def get_search_insights(
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(20, ge=5, le=100),
    user=Depends(get_current_user),
):
    """Search analytics snapshot: trends, entities, diversity, mix and coverage gaps."""
    from app.db.models import Request, Summary

    now = datetime.now(UTC)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    rows = (
        Summary.select(Summary, Request)
        .join(Request)
        .where(
            Request.user_id == user["user_id"],
            Request.created_at >= previous_start,
            Summary.is_deleted == False,  # noqa: E712
        )
        .order_by(Request.created_at.desc())
        .limit(max(limit * 60, 1200))
    )

    tag_rows: list[tuple[datetime, list[str]]] = []
    entity_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    tag_counts_total: Counter[str] = Counter()
    total_articles = 0

    for row in rows:
        payload = ensure_mapping(row.json_payload)
        metadata = ensure_mapping(payload.get("metadata"))
        entities = ensure_mapping(payload.get("entities"))
        created_at = row.request.created_at
        total_articles += 1

        tags = [str(t).strip().lower() for t in (payload.get("topic_tags") or []) if str(t).strip()]
        tag_rows.append((created_at, tags))
        tag_counts_total.update(tags)

        domain = str(metadata.get("domain") or "").strip().lower()
        if domain:
            domain_counts[domain] += 1

        lang = str(row.lang or "unknown").strip().lower()
        lang_counts[lang] += 1

        for bucket in ("people", "organizations", "locations"):
            values = entities.get(bucket) or []
            for value in values[:40]:
                normalized = str(value).strip()
                if normalized:
                    entity_counts[normalized] += 1

        for kw in payload.get("seo_keywords") or []:
            normalized_kw = str(kw).strip().lower()
            if normalized_kw:
                keyword_counts[normalized_kw] += 1

    current_tags = _period_tag_counts(tag_rows, current_start, now)
    previous_tags = _period_tag_counts(tag_rows, previous_start, current_start)

    trending_topics: list[dict[str, Any]] = []
    for tag, count in current_tags.most_common(limit):
        prev = previous_tags.get(tag, 0)
        trend_delta = count - prev
        trend_score = round((count - prev) / prev, 3) if prev > 0 else 1.0 if count > 0 else 0.0
        trending_topics.append(
            {
                "tag": tag,
                "count": count,
                "prev_count": prev,
                "trend_delta": trend_delta,
                "trend_score": trend_score,
            }
        )

    rising_entities = [
        {"entity": entity, "count": count} for entity, count in entity_counts.most_common(limit)
    ]

    source_diversity = {
        "unique_domains": len(domain_counts),
        "top_domains": [
            {"domain": domain, "count": count} for domain, count in domain_counts.most_common(limit)
        ],
    }
    if total_articles > 0:
        entropy = 0.0
        for count in domain_counts.values():
            p = count / total_articles
            if p > 0:
                entropy -= p * math.log2(p)
        source_diversity["shannon_entropy"] = round(entropy, 4)
    else:
        source_diversity["shannon_entropy"] = 0.0

    language_mix = {
        "total": total_articles,
        "languages": [
            {
                "language": lang,
                "count": count,
                "ratio": round((count / total_articles), 4) if total_articles else 0.0,
            }
            for lang, count in lang_counts.most_common(limit)
        ],
    }

    # Coverage gaps: keywords seen often in summaries but not reflected in topic tags.
    tag_tokens = {tag.lstrip("#") for tag in tag_counts_total}
    gaps: list[dict[str, Any]] = []
    for keyword, count in keyword_counts.most_common(limit * 4):
        if keyword in tag_tokens:
            continue
        if count < 2:
            continue
        gaps.append(
            {
                "term": keyword,
                "mentions": count,
                "tag_coverage": 0,
                "gap_score": round(count / max(1, total_articles), 4),
            }
        )
        if len(gaps) >= limit:
            break

    payload = {
        "period_days": days,
        "window": {
            "start": current_start.isoformat().replace("+00:00", "Z"),
            "end": now.isoformat().replace("+00:00", "Z"),
        },
        "topic_trends": trending_topics,
        "rising_entities": rising_entities,
        "source_diversity": source_diversity,
        "language_mix": language_mix,
        "coverage_gaps": gaps,
    }
    pagination = {"total": len(trending_topics), "limit": limit, "offset": 0, "has_more": False}
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
