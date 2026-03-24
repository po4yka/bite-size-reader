"""Search orchestration for API endpoints."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.api.dependencies.search_resources import get_chroma_search_service
from app.api.models.responses import PaginationInfo, SearchResultsData
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
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.application.use_cases.search_read_model import SearchReadModelUseCase


class SearchService:
    """Owns search ranking, semantic enrichment, and related projections."""

    def __init__(
        self,
        *,
        search_read_model: SearchReadModelUseCase,
        get_chroma_service: Callable[..., Awaitable[Any]] = get_chroma_search_service,
    ) -> None:
        self._search_read_model = search_read_model
        self._get_chroma_service = get_chroma_service

    async def search_summaries(
        self,
        *,
        q: str,
        user_id: int,
        limit: int,
        offset: int,
        mode: str,
        min_similarity: float,
        filters: SearchFilters,
    ) -> SearchResultsData:
        intent = infer_intent(q)
        resolved_mode = resolve_mode(mode, intent)
        fetch_limit = min(300, max(limit * 4, limit + 25))
        fts_query = re.sub(r"#", " ", q).strip() or q
        fts_results, _ = await self._search_read_model.fts_search_paginated(
            fts_query,
            limit=fetch_limit,
            offset=0,
            user_id=user_id,
        )
        fts_by_request_id = build_fts_hits(fts_results)
        semantic_by_request_id = await build_semantic_hits(
            q=q,
            resolved_mode=resolved_mode,
            filters=filters,
            user_id=user_id,
            fetch_limit=fetch_limit,
            min_similarity=min_similarity,
            get_chroma_service=self._get_chroma_service,
        )
        request_ids = candidate_request_ids(
            resolved_mode,
            fts_by_request_id,
            semantic_by_request_id,
        )
        requests_map = await self._search_read_model.get_requests_by_ids(
            request_ids,
            user_id=user_id,
        )
        summaries_map = await self._search_read_model.get_summaries_by_request_ids(
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
        return SearchResultsData(
            results=result_models,
            pagination=pagination,
            query=q,
            intent=intent,
            mode=resolved_mode,
            facets=facets,
        )

    async def semantic_search_summaries(
        self,
        *,
        q: str,
        user_id: int,
        limit: int,
        offset: int,
        user_scope: str | None,
        min_similarity: float,
        filters: SearchFilters,
    ) -> SearchResultsData:
        chroma_service = await self._get_chroma_service()
        search_results = await chroma_service.search(
            q,
            language=filters.language,
            tags=filters.tags,
            user_scope=user_scope,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        request_ids = [result.request_id for result in search_results.results]
        requests_map = await self._search_read_model.get_requests_by_ids(
            request_ids,
            user_id=user_id,
        )
        summaries_map = await self._search_read_model.get_summaries_by_request_ids(
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
        return SearchResultsData(
            results=result_models,
            pagination=pagination,
            query=q,
            intent=infer_intent(q),
            mode="semantic",
            facets=facets,
        )

    async def get_search_insights(
        self,
        *,
        user_id: int,
        days: int,
        limit: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        now = datetime.now(UTC)
        current_start = now - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)
        rows = await self._search_read_model.get_search_insight_rows(
            user_id=user_id,
            previous_start=previous_start,
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
        return payload, pagination

    async def get_related_summaries(
        self,
        *,
        user_id: int,
        tag: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        normalized_tag = tag if tag.startswith("#") else f"#{tag}"
        summaries_list, _, _ = await self._search_read_model.get_user_summaries(
            user_id,
            limit=limit,
            offset=offset,
        )
        matching_summaries = []
        for summary in summaries_list:
            json_payload = ensure_mapping(summary.get("json_payload"))
            topic_tags = json_payload.get("topic_tags", [])
            if not isinstance(topic_tags, list):
                topic_tags = []

            if normalized_tag.lower() in [t.lower() for t in topic_tags if isinstance(t, str)]:
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
        return {
            "tag": normalized_tag,
            "summaries": matching_summaries,
            "pagination": pagination,
        }

    async def check_duplicate(
        self,
        *,
        user_id: int,
        url: str,
        include_summary: bool,
    ) -> dict[str, Any]:
        from app.core.url_utils import compute_dedupe_hash, normalize_url

        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(normalized)
        existing, summary = await self._search_read_model.get_duplicate_request_and_summary(
            user_id=user_id,
            dedupe_hash=dedupe_hash,
        )
        if not existing:
            return {
                "is_duplicate": False,
                "normalized_url": normalized,
                "dedupe_hash": dedupe_hash,
            }

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

        return response_data
