"""Semantic search service backed by Chroma vector store."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from chromadb.errors import ChromaError
from pydantic import BaseModel, ConfigDict, Field

from app.core.lang import detect_language
from app.infrastructure.vector.chroma_schemas import ChromaQueryFilters

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.infrastructure.vector.chroma_store import ChromaVectorStore
    from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ChromaVectorSearchResult(BaseModel):
    """Normalized result returned by Chroma vector queries."""

    model_config = ConfigDict(frozen=True)

    request_id: int
    summary_id: int
    similarity_score: float = Field(ge=0.0, le=1.0)
    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    tags: list[str] = Field(default_factory=list)
    language: str | None = None


class ChromaVectorSearchResults(BaseModel):
    """Collection of Chroma search results with pagination hints."""

    model_config = ConfigDict(frozen=True)

    results: list[ChromaVectorSearchResult]
    has_more: bool = False


class ChromaVectorSearchService:
    """Run semantic search queries against Chroma using request metadata."""

    def __init__(
        self,
        *,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService,
        default_top_k: int = 25,
    ) -> None:
        if default_top_k <= 0:
            msg = "default_top_k must be positive"
            raise ValueError(msg)

        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._default_top_k = default_top_k

    async def search(
        self,
        query: str,
        *,
        language: str | None = None,
        tags: Iterable[str] | None = None,
        user_scope: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ChromaVectorSearchResults:
        """Search Chroma for summaries similar to the query text."""

        if not query or not query.strip():
            logger.warning("chroma_search_empty_query")
            return ChromaVectorSearchResults(results=[], has_more=False)

        requested_limit = limit or self._default_top_k
        fetch_limit = requested_limit + offset + 1  # +1 to detect has_more

        detected_language = language or detect_language(query)

        try:
            query_embedding = await self._embedding_service.generate_embedding(
                query.strip(), language=detected_language
            )
        except Exception:
            logger.exception(
                "chroma_search_embedding_failed",
                extra={"language": detected_language},
            )
            return ChromaVectorSearchResults(results=[], has_more=False)

        effective_scope = user_scope or getattr(self._vector_store, "user_scope", None)
        filters = ChromaQueryFilters(
            environment=getattr(self._vector_store, "environment", "dev"),
            user_scope=effective_scope or "public",
            language=detected_language,
            tags=list(tags) if tags else [],
        ).to_where()

        try:
            raw = await asyncio.to_thread(
                self._vector_store.query,
                query_embedding,
                filters,
                fetch_limit,
            )
        except ChromaError:
            logger.exception("chroma_search_query_failed")
            return ChromaVectorSearchResults(results=[], has_more=False)
        except Exception:
            logger.exception("chroma_search_unexpected_error")
            return ChromaVectorSearchResults(results=[], has_more=False)

        metadatas = raw.get("metadatas") or []
        distances = raw.get("distances") or []

        if not metadatas or not isinstance(metadatas, list):
            return ChromaVectorSearchResults(results=[], has_more=False)

        first_batch = metadatas[0] or []
        distance_batch = distances[0] if distances else []

        results: list[ChromaVectorSearchResult] = []

        for idx, metadata in enumerate(first_batch):
            if not isinstance(metadata, dict):
                continue

            request_id = self._safe_int(metadata.get("request_id"))
            summary_id = self._safe_int(metadata.get("summary_id"))

            if request_id is None or summary_id is None:
                continue

            similarity_score = self._compute_similarity(distance_batch, idx)
            snippet = metadata.get("text")
            if snippet and len(str(snippet)) > 300:
                snippet = str(snippet)[:297] + "..."

            results.append(
                ChromaVectorSearchResult(
                    request_id=request_id,
                    summary_id=summary_id,
                    similarity_score=similarity_score,
                    url=metadata.get("url"),
                    title=metadata.get("title"),
                    snippet=snippet,
                    tags=self._normalize_tags(metadata.get("tags")),
                    language=metadata.get("language"),
                )
            )

        has_more = len(results) > offset + requested_limit
        return ChromaVectorSearchResults(
            results=results[offset : offset + requested_limit],
            has_more=has_more,
        )

    async def find_duplicates(
        self,
        text: str,
        *,
        threshold: float = 0.95,
        language: str | None = None,
        user_scope: str | None = None,
    ) -> list[ChromaVectorSearchResult]:
        """Find content that is highly similar to the input text."""
        results = await self.search(
            text,
            language=language,
            user_scope=user_scope,
            limit=5,
        )
        return [r for r in results.results if r.similarity_score >= threshold]

    @staticmethod
    def _compute_similarity(distances: list[float], idx: int) -> float:
        distance = 0.0
        if 0 <= idx < len(distances):
            try:
                distance = float(distances[idx])
            except (TypeError, ValueError):
                distance = 0.0

        if 0.0 <= distance <= 1.0:
            return max(0.0, 1.0 - distance)
        return 1.0 / (1.0 + distance) if distance >= 0 else 0.0

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_tags(tags: Any) -> list[str]:
        if not tags:
            return []
        if isinstance(tags, str):
            return [tags]
        if isinstance(tags, list | tuple | set):
            clean: list[str] = []
            for tag in tags:
                text = str(tag).strip()
                if text:
                    clean.append(text)
            return clean
        return []

    @staticmethod
    def _build_filters(
        *, language: str | None, tags: Iterable[str] | None, user_scope: str | None
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        if language:
            filters["language"] = language

        normalized_tags = [tag for tag in (tags or []) if str(tag).strip()]
        if normalized_tags:
            filters["$and"] = [{"tags": {"$contains": tag}} for tag in normalized_tags]

        if user_scope:
            filters["user_scope"] = user_scope

        return filters
