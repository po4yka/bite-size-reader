from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.di.types import SearchDependencies
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.chroma_vector_search_service import ChromaVectorSearchService
from app.services.embedding_factory import create_embedding_service
from app.services.hybrid_search_service import HybridSearchService
from app.services.query_expansion_service import QueryExpansionService
from app.services.reranking_service import OpenRouterRerankingService
from app.services.summary_embedding_generator import SummaryEmbeddingGenerator
from app.services.topic_search import LocalTopicSearchService, TopicSearchService

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_SEARCH_MAX_RESULTS = 5


def get_topic_search_limit(cfg: AppConfig) -> int:
    raw_value = cfg.runtime.topic_search_max_results
    try:
        limit = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("topic_search_limit_invalid", extra={"value": raw_value})
        return DEFAULT_TOPIC_SEARCH_MAX_RESULTS

    if limit <= 0:
        logger.warning("topic_search_limit_non_positive", extra={"value": limit})
        return DEFAULT_TOPIC_SEARCH_MAX_RESULTS

    if limit > 10:
        logger.warning("topic_search_limit_too_large", extra={"value": limit})
        return 10

    return limit


def build_search_dependencies(
    cfg: AppConfig,
    db: DatabaseSessionManager,
    *,
    llm_client: Any,
    audit_func: Callable[[str, str, dict[str, Any]], None],
    firecrawl_client: Any | None = None,
    topic_search_max_results: int | None = None,
) -> SearchDependencies:
    """Build the shared local, vector, and hybrid search stack."""
    max_results = topic_search_max_results or get_topic_search_limit(cfg)
    vector_store: ChromaVectorStore | None = None

    try:
        vector_store = ChromaVectorStore(
            host=cfg.vector_store.host,
            auth_token=cfg.vector_store.auth_token,
            environment=cfg.vector_store.environment,
            user_scope=cfg.vector_store.user_scope,
            collection_version=cfg.vector_store.collection_version,
            required=cfg.vector_store.required,
            connection_timeout=cfg.vector_store.connection_timeout,
        )
        if not vector_store.available:
            logger.warning(
                "chroma_not_available_continuing",
                extra={"host": cfg.vector_store.host},
            )
    except Exception as exc:
        logger.warning(
            "chroma_init_failed_continuing_without_vector_search",
            extra={"error": str(exc), "host": cfg.vector_store.host},
        )
        vector_store = None

    local_searcher = LocalTopicSearchService(
        db=db,
        max_results=max_results,
        audit_func=audit_func,
    )
    topic_searcher = (
        TopicSearchService(
            firecrawl=firecrawl_client,
            max_results=max_results,
            audit_func=audit_func,
        )
        if firecrawl_client is not None
        else None
    )
    embedding_service = create_embedding_service(cfg.embedding)
    embedding_generator = SummaryEmbeddingGenerator(
        db=db,
        embedding_service=embedding_service,
        max_token_length=cfg.embedding.max_token_length,
    )
    query_expansion_service = QueryExpansionService(max_expansions=5, use_synonyms=True)

    chroma_vector_search_service: ChromaVectorSearchService | None = None
    if vector_store is not None:
        chroma_vector_search_service = ChromaVectorSearchService(
            vector_store=vector_store,
            embedding_service=embedding_service,
            default_top_k=max_results * 2,
        )

    reranking_service = OpenRouterRerankingService(
        client=llm_client,
        top_k=max_results * 2,
        timeout_sec=cfg.runtime.request_timeout_sec,
    )
    hybrid_search_service = HybridSearchService(
        fts_service=local_searcher,
        vector_service=chroma_vector_search_service,
        fts_weight=1.0 if chroma_vector_search_service is None else 0.4,
        vector_weight=0.0 if chroma_vector_search_service is None else 0.6,
        max_results=max_results,
        query_expansion=query_expansion_service,
        reranking=reranking_service,
    )

    return SearchDependencies(
        local_searcher=local_searcher,
        topic_searcher=topic_searcher,
        embedding_service=embedding_service,
        embedding_generator=embedding_generator,
        vector_store=vector_store,
        chroma_vector_search_service=chroma_vector_search_service,
        hybrid_search_service=hybrid_search_service,
        query_expansion_service=query_expansion_service,
    )
