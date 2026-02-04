"""Semantic search service backed by Chroma vector store."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from chromadb.errors import ChromaError
from pydantic import BaseModel, ConfigDict, Field

from app.core.lang import detect_language

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
    text: str | None = None
    source: str | None = None
    published_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    language: str | None = None
    window_id: str | None = None
    window_index: int | None = None
    chunk_id: str | None = None
    neighbor_chunk_ids: list[str] = Field(default_factory=list)
    semantic_boosters: list[str] = Field(default_factory=list)
    local_keywords: list[str] = Field(default_factory=list)
    local_summary: str | None = None
    query_expansion_keywords: list[str] = Field(default_factory=list)
    section: str | None = None
    topics: list[str] = Field(default_factory=list)


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
        correlation_id: str | None = None,
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

        store_scope = getattr(self._vector_store, "user_scope", None) or "public"
        if user_scope and user_scope != store_scope:
            logger.warning(
                "chroma_search_scope_mismatch",
                extra={"requested_scope": user_scope, "store_scope": store_scope},
            )
            return ChromaVectorSearchResults(results=[], has_more=False)

        filters = {
            "language": detected_language,
            "tags": list(tags) if tags else [],
        }

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
            raw_text = metadata.get("text")
            snippet = metadata.get("local_summary") or raw_text
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
                    text=raw_text,
                    source=metadata.get("source"),
                    published_at=metadata.get("published_at"),
                    tags=self._normalize_tags(metadata.get("tags")),
                    language=metadata.get("language"),
                    window_id=metadata.get("window_id"),
                    window_index=self._safe_int(metadata.get("window_index")),
                    chunk_id=metadata.get("chunk_id"),
                    neighbor_chunk_ids=self._normalize_tags(metadata.get("neighbor_chunk_ids")),
                    semantic_boosters=self._normalize_tags(metadata.get("semantic_boosters")),
                    local_keywords=self._normalize_tags(metadata.get("local_keywords")),
                    local_summary=metadata.get("local_summary"),
                    query_expansion_keywords=self._normalize_tags(
                        metadata.get("query_expansion_keywords")
                    ),
                    section=metadata.get("section"),
                    topics=self._normalize_tags(metadata.get("topics")),
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
        if idx < 0 or idx >= len(distances):
            return 0.0
        try:
            distance = float(distances[idx])
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, 1.0 - distance))

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
