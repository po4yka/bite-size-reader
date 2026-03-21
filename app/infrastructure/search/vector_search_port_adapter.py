"""Application-port adapter for vector search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dto.vector_search import VectorSearchHitDTO

if TYPE_CHECKING:
    from app.infrastructure.search.vector_search_service import VectorSearchService


class VectorSearchPortAdapter:
    """Adapt the infrastructure vector search service to the application port."""

    def __init__(self, service: VectorSearchService) -> None:
        self._service = service

    async def search(
        self,
        query: str,
        *,
        correlation_id: str | None = None,
    ) -> list[VectorSearchHitDTO]:
        results = await self._service.search(query, correlation_id=correlation_id)
        return [
            VectorSearchHitDTO(
                request_id=result.request_id,
                summary_id=result.summary_id,
                similarity_score=result.similarity_score,
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                source=result.source,
                published_at=result.published_at,
            )
            for result in results
        ]
