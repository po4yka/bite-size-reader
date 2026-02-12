"""MCP server exposing Bite-Size Reader articles and search to AI agents.

This module implements a Model Context Protocol (MCP) server that allows
external AI agents (OpenClaw, Claude Desktop, etc.) to:
- Search stored article summaries by keyword, topic, or entity
- Perform semantic (vector) search using ChromaDB embeddings
- Retrieve individual article details with full summary data
- List recent articles with filtering and pagination
- Get database statistics and collection overview

Usage (stdio transport - default for OpenClaw/Claude Desktop):
    python -m app.cli.mcp_server

Usage (SSE transport - for HTTP-based integrations):
    python -m app.cli.mcp_server --transport sse --user-id 12345
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sys
import threading
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Logging — MCP stdio transport requires NO stdout writes, so we direct
# all logging to stderr.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("bsr.mcp")

# ---------------------------------------------------------------------------
# Database bootstrap — we initialise the Peewee proxy *once* at import time
# so that every tool handler can query the DB without re-connecting.
# ---------------------------------------------------------------------------
_DB_PATH = os.getenv("DB_PATH", "/data/app.db")


def _init_database(db_path: str | None = None) -> None:
    """Connect Peewee proxy to the SQLite database file."""
    import peewee

    from app.db.models import database_proxy

    path = db_path or _DB_PATH
    db = peewee.SqliteDatabase(
        path,
        pragmas={
            "journal_mode": "wal",
            "cache_size": -8000,  # 8 MB
            "foreign_keys": 1,
            "busy_timeout": 5000,
        },
    )
    database_proxy.initialize(db)
    db.connect(reuse_if_open=True)
    logger.info("Database connected: %s", path)


# ---------------------------------------------------------------------------
# ChromaDB / semantic search — lazy singleton, optional (graceful degradation)
# ---------------------------------------------------------------------------
_chroma_service: Any = None
_chroma_last_failed_at: float | None = None
_CHROMA_RETRY_INTERVAL_SEC = 60.0
_chroma_init_lock = threading.Lock()
_local_vector_service: Any = None
_local_vector_last_failed_at: float | None = None
_LOCAL_VECTOR_RETRY_INTERVAL_SEC = 60.0
_local_vector_init_lock = threading.Lock()


async def _get_chroma_service() -> Any:
    """Lazily initialise and return the ChromaVectorSearchService singleton.

    Returns None if ChromaDB is unavailable (the semantic_search tool
    will degrade to a helpful error message).
    """
    global _chroma_service, _chroma_last_failed_at

    if _chroma_service is not None:
        return _chroma_service
    now = time.monotonic()
    if (
        _chroma_last_failed_at is not None
        and (now - _chroma_last_failed_at) < _CHROMA_RETRY_INTERVAL_SEC
    ):
        return None

    with _chroma_init_lock:
        if _chroma_service is not None:
            return _chroma_service

        now = time.monotonic()
        if (
            _chroma_last_failed_at is not None
            and (now - _chroma_last_failed_at) < _CHROMA_RETRY_INTERVAL_SEC
        ):
            return None

        try:
            from app.config import load_config
            from app.infrastructure.vector.chroma_store import ChromaVectorStore
            from app.services.chroma_vector_search_service import ChromaVectorSearchService
            from app.services.embedding_service import EmbeddingService

            cfg = load_config(allow_stub_telegram=True).vector_store
            embedding = EmbeddingService()
            store = ChromaVectorStore(
                host=cfg.host,
                auth_token=cfg.auth_token,
                environment=cfg.environment,
                user_scope=cfg.user_scope,
                collection_version=cfg.collection_version,
            )
            _chroma_service = ChromaVectorSearchService(
                vector_store=store,
                embedding_service=embedding,
                default_top_k=100,
            )
            _chroma_last_failed_at = None
            logger.info("ChromaDB search service initialised")
            return _chroma_service
        except Exception:
            _chroma_last_failed_at = time.monotonic()
            logger.warning(
                "ChromaDB unavailable — semantic_search tool will be disabled",
                exc_info=True,
            )
            return None


async def _get_local_vector_service() -> Any:
    """Lazily initialize local embedding service for semantic fallback search."""
    global _local_vector_service, _local_vector_last_failed_at

    if _local_vector_service is not None:
        return _local_vector_service

    now = time.monotonic()
    if (
        _local_vector_last_failed_at is not None
        and (now - _local_vector_last_failed_at) < _LOCAL_VECTOR_RETRY_INTERVAL_SEC
    ):
        return None

    with _local_vector_init_lock:
        if _local_vector_service is not None:
            return _local_vector_service

        now = time.monotonic()
        if (
            _local_vector_last_failed_at is not None
            and (now - _local_vector_last_failed_at) < _LOCAL_VECTOR_RETRY_INTERVAL_SEC
        ):
            return None

        try:
            from app.services.embedding_service import EmbeddingService

            _local_vector_service = EmbeddingService()
            _local_vector_last_failed_at = None
            logger.info("Local vector fallback service initialised")
            return _local_vector_service
        except Exception:
            _local_vector_last_failed_at = time.monotonic()
            logger.warning(
                "Local vector fallback unavailable",
                exc_info=True,
            )
            return None


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "bite-size-reader",
    instructions=(
        "Bite-Size Reader is a personal knowledge base of web article summaries. "
        "Use the tools below to search, retrieve, and explore stored articles. "
        "Articles are summarised with key ideas, topic tags, entities, "
        "reading-time estimates, and more."
    ),
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
_MCP_USER_ID: int | None = None


def _set_user_scope(user_id: int | None) -> None:
    """Configure optional MCP user scope for all DB queries."""
    global _MCP_USER_ID
    _MCP_USER_ID = user_id


def _request_scope_filters(request_model: Any) -> list[Any]:
    """Build request-level visibility filters for MCP queries."""
    filters: list[Any] = [request_model.is_deleted == False]  # noqa: E712
    if _MCP_USER_ID is not None:
        filters.append(request_model.user_id == _MCP_USER_ID)
    return filters


def _collection_scope_filters(collection_model: Any) -> list[Any]:
    """Build collection-level visibility filters for MCP queries."""
    filters: list[Any] = [collection_model.is_deleted == False]  # noqa: E712
    if _MCP_USER_ID is not None:
        filters.append(collection_model.user == _MCP_USER_ID)
    return filters


def _is_loopback_host(host: str) -> bool:
    """Return True when host points to loopback/local interface."""
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def _ensure_mapping(value: Any) -> dict:
    """Safely coerce a value to a dict (handles None, str JSON, etc.)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _isotime(dt: Any) -> str:
    """Convert a datetime to ISO 8601 string."""
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        text = dt.isoformat()
        if text.endswith("Z"):
            return text
        if text.endswith("+00:00"):
            return f"{text[:-6]}Z"
        if getattr(dt, "tzinfo", None) is None:
            return f"{text}Z"
        return text
    return str(dt) if dt else ""


def _format_summary_compact(summary_row: Any, request_row: Any) -> dict:
    """Build a compact summary dict from ORM rows."""
    payload = _ensure_mapping(getattr(summary_row, "json_payload", None))
    metadata = _ensure_mapping(payload.get("metadata"))

    return {
        "summary_id": summary_row.id,
        "request_id": getattr(request_row, "id", None),
        "url": getattr(request_row, "input_url", "") or getattr(request_row, "normalized_url", ""),
        "title": metadata.get("title", "Untitled"),
        "domain": metadata.get("domain", ""),
        "summary_250": payload.get("summary_250", ""),
        "tldr": payload.get("tldr", ""),
        "topic_tags": payload.get("topic_tags", []),
        "reading_time_min": payload.get("estimated_reading_time_min", 0),
        "lang": getattr(summary_row, "lang", "auto"),
        "is_read": getattr(summary_row, "is_read", False),
        "is_favorited": getattr(summary_row, "is_favorited", False),
        "created_at": _isotime(getattr(summary_row, "created_at", None)),
    }


def _format_summary_detail(summary_row: Any, request_row: Any) -> dict:
    """Build a detailed summary dict from ORM rows."""
    payload = _ensure_mapping(getattr(summary_row, "json_payload", None))
    metadata = _ensure_mapping(payload.get("metadata"))
    entities = _ensure_mapping(payload.get("entities"))
    readability = _ensure_mapping(payload.get("readability"))

    return {
        "summary_id": summary_row.id,
        "request_id": getattr(request_row, "id", None),
        "url": getattr(request_row, "input_url", "") or getattr(request_row, "normalized_url", ""),
        "title": metadata.get("title", "Untitled"),
        "domain": metadata.get("domain", ""),
        "author": metadata.get("author"),
        "summary_250": payload.get("summary_250", ""),
        "summary_1000": payload.get("summary_1000", ""),
        "tldr": payload.get("tldr", ""),
        "key_ideas": payload.get("key_ideas", []),
        "topic_tags": payload.get("topic_tags", []),
        "entities": {
            "people": entities.get("people", []),
            "organizations": entities.get("organizations", []),
            "locations": entities.get("locations", []),
        },
        "estimated_reading_time_min": payload.get("estimated_reading_time_min", 0),
        "key_stats": payload.get("key_stats", []),
        "answered_questions": payload.get("answered_questions", []),
        "readability": (
            {
                "method": readability.get("method", ""),
                "score": readability.get("score", 0.0),
                "level": readability.get("level", ""),
            }
            if readability
            else None
        ),
        "seo_keywords": payload.get("seo_keywords", []),
        "lang": getattr(summary_row, "lang", "auto"),
        "is_read": getattr(summary_row, "is_read", False),
        "is_favorited": getattr(summary_row, "is_favorited", False),
        "created_at": _isotime(getattr(summary_row, "created_at", None)),
        "request_status": getattr(request_row, "status", ""),
        "request_type": getattr(request_row, "type", ""),
    }


def _run_async_for_resource(coro: Any) -> str:
    """Run async MCP tool logic from sync resource handlers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return json.dumps({"error": "Resource cannot run async call inside active event loop"})


def _clamp_limit(limit: int, *, minimum: int = 1, maximum: int = 25) -> int:
    """Clamp integer limit values to a safe range."""
    return max(minimum, min(maximum, int(limit)))


def _clamp_similarity(value: float) -> float:
    """Clamp similarity thresholds to [0.0, 1.0]."""
    return max(0.0, min(1.0, float(value)))


def _safe_int(value: Any) -> int | None:
    """Safely cast values to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tokenize(text: str) -> set[str]:
    """Tokenize text for lightweight lexical scoring."""
    if not text:
        return set()
    return {t.lower() for t in re.findall(r"[\w-]{2,}", text, flags=re.UNICODE)}


def _lexical_overlap_score(query: str, text: str) -> float:
    """Compute lightweight lexical overlap score between query and candidate text."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0
    overlap = query_tokens.intersection(text_tokens)
    return len(overlap) / len(query_tokens)


def _cosine_similarity(query_vector: list[float], candidate_vector: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not query_vector or not candidate_vector:
        return 0.0

    dot = 0.0
    query_norm = 0.0
    candidate_norm = 0.0
    for q, c in zip(query_vector, candidate_vector, strict=False):
        qf = float(q)
        cf = float(c)
        dot += qf * cf
        query_norm += qf * qf
        candidate_norm += cf * cf

    if query_norm <= 0.0 or candidate_norm <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (math.sqrt(query_norm) * math.sqrt(candidate_norm))))


def _extract_query_tags(text: str) -> list[str]:
    """Extract hashtag tags from query text."""
    if not text:
        return []
    tags = [f"#{match.lower()}" for match in re.findall(r"#([\w-]{1,50})", text, flags=re.UNICODE)]
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)
    return ordered


def _extract_semantic_seed_text(payload: dict[str, Any]) -> str:
    """Build semantic seed text from summary payload."""
    metadata = _ensure_mapping(payload.get("metadata"))
    pieces: list[str] = []
    for value in (
        metadata.get("title"),
        payload.get("summary_250"),
        payload.get("tldr"),
        payload.get("summary_1000"),
    ):
        if value:
            pieces.append(str(value))
    for idea in payload.get("key_ideas", [])[:5]:
        if idea:
            pieces.append(str(idea))
    for tag in payload.get("topic_tags", [])[:8]:
        if tag:
            pieces.append(str(tag))
    return " ".join(pieces).strip()


def _fetch_summaries_by_ids(summary_ids: list[int]) -> dict[int, tuple[Any, Any]]:
    """Fetch summaries and requests in one query, keyed by summary id."""
    from app.db.models import Request, Summary

    if not summary_ids:
        return {}

    rows = (
        Summary.select(Summary, Request)
        .join(Request)
        .where(
            Summary.id.in_(summary_ids),
            Summary.is_deleted == False,  # noqa: E712
            *_request_scope_filters(Request),
        )
    )

    result: dict[int, tuple[Any, Any]] = {}
    for summary in rows:
        result[int(summary.id)] = (summary, summary.request)
    return result


def _semantic_match_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize chunk/window match metadata for semantic result output."""
    preview = row.get("local_summary") or row.get("snippet") or row.get("text")
    preview_text = str(preview) if preview else ""
    if len(preview_text) > 320:
        preview_text = preview_text[:317] + "..."

    return {
        "similarity_score": round(float(row.get("similarity_score", 0.0)), 4),
        "window_id": row.get("window_id"),
        "window_index": row.get("window_index"),
        "chunk_id": row.get("chunk_id"),
        "section": row.get("section"),
        "topics": row.get("topics") or [],
        "keywords": row.get("local_keywords") or [],
        "semantic_boosters": row.get("semantic_boosters") or [],
        "preview": preview_text,
    }


def _build_semantic_results(
    *,
    query: str,
    rows: list[dict[str, Any]],
    backend: str,
    limit: int,
    include_chunks: bool,
    rerank: bool,
) -> list[dict[str, Any]]:
    """Group semantic rows by summary and return enriched compact payloads."""
    grouped: dict[int, dict[str, Any]] = {}

    for row in rows:
        raw_summary_id = row.get("summary_id")
        try:
            summary_id = int(raw_summary_id)
        except (TypeError, ValueError):
            continue

        score = float(row.get("similarity_score", 0.0))
        group = grouped.get(summary_id)
        if group is None:
            group = {
                "summary_id": summary_id,
                "similarity_score": score,
                "best_row": row,
                "matches": [],
            }
            grouped[summary_id] = group
        elif score > float(group.get("similarity_score", 0.0)):
            group["similarity_score"] = score
            group["best_row"] = row

        if include_chunks:
            match = _semantic_match_from_row(row)
            signature = (
                match.get("window_id"),
                match.get("chunk_id"),
                match.get("section"),
                match.get("preview"),
            )
            seen_signatures = group.setdefault("seen_signatures", set())
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                group["matches"].append(match)

    if not grouped:
        return []

    summary_map = _fetch_summaries_by_ids(list(grouped.keys()))
    results: list[dict[str, Any]] = []

    for summary_id, group in grouped.items():
        summary_bundle = summary_map.get(summary_id)
        if summary_bundle is None:
            continue
        summary_row, request_row = summary_bundle
        compact = _format_summary_compact(summary_row, request_row)
        compact["similarity_score"] = round(float(group["similarity_score"]), 4)
        compact["search_backend"] = backend

        best_row = group.get("best_row") or {}
        compact["semantic_context"] = {
            "section": best_row.get("section"),
            "topics": best_row.get("topics") or [],
            "keywords": best_row.get("local_keywords") or [],
        }

        if include_chunks:
            matches = sorted(
                group.get("matches", []),
                key=lambda item: item.get("similarity_score", 0.0),
                reverse=True,
            )
            compact["semantic_matches"] = matches[:5]
            compact["semantic_match_count"] = len(matches)
            compact["best_match"] = matches[0] if matches else None

        results.append(compact)

    if rerank and results:
        for result in results:
            text = " ".join(
                [
                    str(result.get("title") or ""),
                    str(result.get("summary_250") or ""),
                    str(result.get("tldr") or ""),
                    str(_ensure_mapping(result.get("best_match")).get("preview") or ""),
                ]
            )
            lexical = _lexical_overlap_score(query, text)
            result["rerank_score"] = round(
                0.82 * float(result.get("similarity_score", 0.0)) + 0.18 * lexical, 4
            )

        results.sort(key=lambda item: float(item.get("rerank_score", 0.0)), reverse=True)
    else:
        results.sort(key=lambda item: float(item.get("similarity_score", 0.0)), reverse=True)

    return results[:limit]


async def _search_local_vectors(
    query: str,
    *,
    language: str | None,
    limit: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Semantic search fallback over locally stored summary embeddings."""
    from app.db.models import Request, Summary, SummaryEmbedding

    embedding_service = await _get_local_vector_service()
    if embedding_service is None:
        return []

    try:
        query_vector_any = await embedding_service.generate_embedding(
            query.strip(), language=language
        )
    except Exception:
        logger.exception("local_vector_query_embedding_failed")
        return []

    query_vector = (
        query_vector_any.tolist() if hasattr(query_vector_any, "tolist") else list(query_vector_any)
    )
    if not query_vector:
        return []

    scan_limit = max(limit * 80, 600)
    query_rows = (
        SummaryEmbedding.select(SummaryEmbedding, Summary, Request)
        .join(Summary)
        .join(Request)
        .where(
            Summary.is_deleted == False,  # noqa: E712
            *_request_scope_filters(Request),
        )
        .order_by(SummaryEmbedding.created_at.desc())
        .limit(scan_limit)
    )

    if language:
        query_rows = query_rows.where((Summary.lang == language) | (Summary.lang.is_null(True)))

    results: list[dict[str, Any]] = []
    for row in query_rows:
        try:
            candidate = embedding_service.deserialize_embedding(row.embedding_blob)
        except Exception:
            continue

        similarity = _cosine_similarity(query_vector, candidate)
        if similarity < min_similarity:
            continue

        payload = _ensure_mapping(getattr(row.summary, "json_payload", None))
        metadata = _ensure_mapping(payload.get("metadata"))
        snippet = payload.get("summary_250") or payload.get("tldr")

        results.append(
            {
                "request_id": getattr(row.summary.request, "id", None),
                "summary_id": getattr(row.summary, "id", None),
                "similarity_score": similarity,
                "url": getattr(row.summary.request, "input_url", None)
                or getattr(row.summary.request, "normalized_url", None),
                "title": metadata.get("title"),
                "snippet": snippet,
                "text": payload.get("summary_1000") or snippet,
                "source": metadata.get("domain"),
                "published_at": metadata.get("published_at"),
                "local_summary": snippet,
                "topics": payload.get("topic_tags", []),
                "local_keywords": payload.get("seo_keywords", []),
            }
        )

    results.sort(key=lambda item: float(item.get("similarity_score", 0.0)), reverse=True)
    return results[: max(limit * 4, limit)]


async def _run_semantic_candidates(
    query: str,
    *,
    language: str | None,
    limit: int,
    min_similarity: float,
    include_chunks: bool,
    rerank: bool,
    allow_keyword_fallback: bool,
) -> dict[str, Any]:
    """Run semantic search with Chroma -> local vectors -> keyword fallback chain."""
    limit = _clamp_limit(limit)
    min_similarity = _clamp_similarity(min_similarity)
    fetch_limit = max(limit * 6, limit + 8)

    chroma = await _get_chroma_service()
    if chroma is not None:
        try:
            chroma_results = await chroma.search(
                query.strip(),
                language=language,
                tags=_extract_query_tags(query),
                user_id=_MCP_USER_ID,
                limit=fetch_limit,
                offset=0,
            )

            chroma_rows: list[dict[str, Any]] = []
            for hit in chroma_results.results:
                if float(hit.similarity_score) < min_similarity:
                    continue
                chroma_rows.append(
                    {
                        "request_id": hit.request_id,
                        "summary_id": hit.summary_id,
                        "similarity_score": hit.similarity_score,
                        "url": hit.url,
                        "title": hit.title,
                        "snippet": hit.snippet,
                        "text": hit.text,
                        "source": hit.source,
                        "published_at": hit.published_at,
                        "window_id": hit.window_id,
                        "window_index": hit.window_index,
                        "chunk_id": hit.chunk_id,
                        "section": hit.section,
                        "topics": hit.topics,
                        "local_keywords": hit.local_keywords,
                        "semantic_boosters": hit.semantic_boosters,
                        "local_summary": hit.local_summary,
                    }
                )

            enriched = _build_semantic_results(
                query=query,
                rows=chroma_rows,
                backend="chroma",
                limit=limit,
                include_chunks=include_chunks,
                rerank=rerank,
            )
            if enriched:
                return {
                    "results": enriched,
                    "has_more": bool(chroma_results.has_more),
                    "search_type": "semantic",
                    "search_backend": "chroma",
                }
        except Exception:
            logger.exception("semantic_chroma_search_failed")

    local_rows = await _search_local_vectors(
        query,
        language=language,
        limit=fetch_limit,
        min_similarity=min_similarity,
    )
    enriched_local = _build_semantic_results(
        query=query,
        rows=local_rows,
        backend="local_vector",
        limit=limit,
        include_chunks=include_chunks,
        rerank=rerank,
    )
    if enriched_local:
        return {
            "results": enriched_local,
            "has_more": len(enriched_local) >= limit and len(local_rows) > len(enriched_local),
            "search_type": "semantic",
            "search_backend": "local_vector",
        }

    if allow_keyword_fallback:
        keyword_payload = _ensure_mapping(search_articles(query=query, limit=limit))
        keyword_results = keyword_payload.get("results")
        if not isinstance(keyword_results, list):
            keyword_results = []
        return {
            "results": keyword_results[:limit],
            "has_more": bool(keyword_payload.get("total", 0) > limit),
            "search_type": "keyword_fallback",
            "search_backend": "fts",
        }

    return {
        "results": [],
        "has_more": False,
        "search_type": "semantic",
        "search_backend": "none",
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def search_articles(query: str, limit: int = 10) -> str:
    """Search stored article summaries by keyword, topic, or entity.

    Performs full-text search across article titles, summaries, tags,
    and entities. Returns matching articles ranked by relevance.

    Args:
        query: Search query (keywords, topic tags like #ai, entity names, etc.)
        limit: Maximum number of results to return (1-25, default 10).
    """
    from app.db.models import Request, Summary, TopicSearchIndex

    limit = max(1, min(25, limit))

    try:
        # Phase 1: FTS5 search
        fts_results = (
            TopicSearchIndex.search(query)
            .select(TopicSearchIndex.request_id, TopicSearchIndex.rank())
            .limit(limit)
            .dicts()
        )
        fts_list = list(fts_results)

        if not fts_list:
            # Phase 2: Fallback — scan summaries with basic matching
            return _fallback_search(query, limit)

        ranked_request_ids: list[int] = []
        seen_request_ids: set[int] = set()
        for row in fts_list:
            raw_request_id = row.get("request_id")
            if raw_request_id in (None, ""):
                continue
            try:
                request_id = int(raw_request_id)
            except (TypeError, ValueError):
                continue
            if request_id in seen_request_ids:
                continue
            seen_request_ids.add(request_id)
            ranked_request_ids.append(request_id)

        if not ranked_request_ids:
            return json.dumps({"results": [], "total": 0, "query": query})

        rank_position = {request_id: idx for idx, request_id in enumerate(ranked_request_ids)}

        # Load summaries for matched requests and keep FTS relevance ordering.
        summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Request.id.in_(ranked_request_ids),
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
        )

        by_request_id: dict[int, dict[str, Any]] = {}
        for s in summaries:
            req = s.request
            rid = int(req.id)
            if rid not in by_request_id:
                by_request_id[rid] = _format_summary_compact(s, req)

        ordered_request_ids = sorted(
            by_request_id.keys(),
            key=lambda rid: rank_position.get(rid, len(rank_position)),
        )
        results = [by_request_id[rid] for rid in ordered_request_ids][:limit]

        return json.dumps({"results": results, "total": len(results), "query": query}, default=str)

    except Exception as exc:
        logger.exception("search_articles failed")
        return json.dumps({"error": str(exc), "query": query})


def _fallback_search(query: str, limit: int) -> str:
    """Simple fallback search scanning summary JSON payloads."""
    from app.db.models import Request, Summary

    query_lower = query.lower()
    terms = query_lower.split()

    all_summaries = (
        Summary.select(Summary, Request)
        .join(Request)
        .where(
            Summary.is_deleted == False,  # noqa: E712
            *_request_scope_filters(Request),
        )
        .order_by(Summary.created_at.desc())
        .limit(200)  # scan cap
    )

    results = []
    for s in all_summaries:
        payload = _ensure_mapping(getattr(s, "json_payload", None))
        searchable = " ".join(
            [
                str(payload.get("summary_250", "")),
                str(payload.get("tldr", "")),
                " ".join(payload.get("topic_tags", [])),
                " ".join(payload.get("seo_keywords", [])),
                str(_ensure_mapping(payload.get("metadata")).get("title", "")),
            ]
        ).lower()

        if any(t in searchable for t in terms):
            results.append(_format_summary_compact(s, s.request))
            if len(results) >= limit:
                break

    return json.dumps({"results": results, "total": len(results), "query": query}, default=str)


@mcp.tool()
def get_article(summary_id: int) -> str:
    """Get full details of an article summary by its ID.

    Returns the complete summary including key ideas, entities,
    topic tags, reading time, readability score, and more.

    Args:
        summary_id: The numeric ID of the summary to retrieve.
    """
    from app.db.models import Request, Summary

    try:
        summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.id == summary_id,
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .get()
        )
        detail = _format_summary_detail(summary, summary.request)
        return json.dumps(detail, default=str)

    except Summary.DoesNotExist:
        return json.dumps({"error": f"Summary {summary_id} not found"})
    except Exception as exc:
        logger.exception("get_article failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def list_articles(
    limit: int = 20,
    offset: int = 0,
    is_favorited: bool | None = None,
    lang: str | None = None,
    tag: str | None = None,
) -> str:
    """List stored article summaries with optional filters.

    Returns a paginated list of articles sorted by most-recent first.

    Args:
        limit: Number of articles to return (1-100, default 20).
        offset: Pagination offset (default 0).
        is_favorited: If set, filter to only favorited (true) or non-favorited (false) articles.
        lang: Filter by detected language code (e.g. "en", "ru").
        tag: Filter by topic tag (e.g. "#ai" or "ai" — the leading # is optional).
    """
    from app.db.models import Request, Summary

    limit = max(1, min(100, limit))
    offset = max(0, offset)

    try:
        query = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
        )

        if is_favorited is not None:
            query = query.where(Summary.is_favorited == is_favorited)

        if lang:
            query = query.where(Summary.lang == lang)

        ordered_query = query.order_by(Summary.created_at.desc())

        if tag:
            tag_normalized = tag if tag.startswith("#") else f"#{tag}"
            tag_lower = tag_normalized.lower()
            matched_articles: list[dict[str, Any]] = []
            for s in ordered_query:
                compact = _format_summary_compact(s, s.request)
                tags = compact.get("topic_tags", [])
                if tag_lower in [str(t).lower() for t in tags]:
                    matched_articles.append(compact)

            total = len(matched_articles)
            results = matched_articles[offset : offset + limit]
        else:
            total = query.count()
            articles = ordered_query.offset(offset).limit(limit)
            results = [_format_summary_compact(s, s.request) for s in articles]

        return json.dumps(
            {
                "articles": results,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(results)) < total,
            },
            default=str,
        )

    except Exception as exc:
        logger.exception("list_articles failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_article_content(summary_id: int) -> str:
    """Get the full extracted content (markdown/text) of an article.

    Returns the original crawled content that was used to generate
    the summary. Useful for reading the full article offline.

    Args:
        summary_id: The numeric ID of the summary whose content to retrieve.
    """
    from app.db.models import CrawlResult, Request, Summary

    try:
        summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.id == summary_id,
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .get()
        )

        request = summary.request
        crawl = (
            CrawlResult.select()
            .where(
                CrawlResult.request == request.id,
                CrawlResult.is_deleted == False,  # noqa: E712
            )
            .first()
        )

        if not crawl:
            return json.dumps({"error": f"No crawl content found for summary {summary_id}"})

        content = crawl.content_markdown or crawl.content_html or request.content_text or ""
        metadata = _ensure_mapping(crawl.metadata_json)

        return json.dumps(
            {
                "summary_id": summary_id,
                "url": getattr(request, "input_url", ""),
                "title": metadata.get("title", "Untitled"),
                "content_format": "markdown" if crawl.content_markdown else "text",
                "content": content[:50000],  # Cap at 50k chars to stay within token limits
                "content_length": len(content),
                "truncated": len(content) > 50000,
            },
            default=str,
        )

    except Summary.DoesNotExist:
        return json.dumps({"error": f"Summary {summary_id} not found"})
    except Exception as exc:
        logger.exception("get_article_content failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_stats() -> str:
    """Get statistics about the Bite-Size Reader article database.

    Returns counts of total articles, unread articles, favorites,
    language breakdown, and top topic tags.
    """
    from app.db.models import Request, Summary

    try:
        scoped_summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
        )

        total = scoped_summaries.count()
        unread = scoped_summaries.where(
            Summary.is_read == False,  # noqa: E712
        ).count()
        favorited = scoped_summaries.where(
            Summary.is_favorited == True,  # noqa: E712
        ).count()

        # Language breakdown
        lang_counts: dict[str, int] = {}
        for row in scoped_summaries.select(Summary.lang).dicts():
            lang = row.get("lang") or "unknown"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        # Top tags (sample recent 200 summaries)
        tag_counts: dict[str, int] = {}
        recent = (
            scoped_summaries.select(Summary.json_payload)
            .order_by(Summary.created_at.desc())
            .limit(200)
        )
        for row in recent:
            payload = _ensure_mapping(getattr(row, "json_payload", None))
            for tag in payload.get("topic_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        # Request type breakdown
        url_count = (
            Request.select().where(*_request_scope_filters(Request), Request.type == "url").count()
        )
        forward_count = (
            Request.select()
            .where(*_request_scope_filters(Request), Request.type == "forward")
            .count()
        )

        return json.dumps(
            {
                "total_articles": total,
                "unread": unread,
                "favorited": favorited,
                "languages": lang_counts,
                "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
                "request_types": {"url": url_count, "forward": forward_count},
            },
            default=str,
        )

    except Exception as exc:
        logger.exception("get_stats failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def find_by_entity(entity_name: str, entity_type: str | None = None, limit: int = 10) -> str:
    """Find articles that mention a specific entity (person, organization, location).

    Searches through the extracted entities in article summaries.

    Args:
        entity_name: Name of the entity to search for (e.g. "OpenAI", "Elon Musk", "San Francisco").
        entity_type: Optional entity type filter: "people", "organizations", or "locations".
        limit: Maximum results to return (1-25, default 10).
    """
    from app.db.models import Request, Summary

    limit = max(1, min(25, limit))
    name_lower = entity_name.lower()

    try:
        all_summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
            .limit(500)  # scan cap
        )

        results = []
        for s in all_summaries:
            payload = _ensure_mapping(getattr(s, "json_payload", None))
            entities = _ensure_mapping(payload.get("entities"))

            types_to_check = (
                [entity_type]
                if entity_type in ("people", "organizations", "locations")
                else ["people", "organizations", "locations"]
            )

            matched = False
            for etype in types_to_check:
                entity_list = entities.get(etype, [])
                for e in entity_list:
                    if name_lower in str(e).lower():
                        matched = True
                        break
                if matched:
                    break

            if matched:
                results.append(_format_summary_compact(s, s.request))
                if len(results) >= limit:
                    break

        return json.dumps(
            {
                "results": results,
                "total": len(results),
                "entity": entity_name,
                "entity_type": entity_type,
            },
            default=str,
        )

    except Exception as exc:
        logger.exception("find_by_entity failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def list_collections(limit: int = 20, offset: int = 0) -> str:
    """List article collections (folders/reading lists).

    Collections are hierarchical and can contain article summaries.
    Returns top-level collections by default.

    Args:
        limit: Number of collections to return (1-50, default 20).
        offset: Pagination offset (default 0).
    """
    from app.db.models import Collection, CollectionItem

    limit = max(1, min(50, limit))
    offset = max(0, offset)

    try:
        query = Collection.select().where(
            Collection.parent.is_null(True), *_collection_scope_filters(Collection)
        )
        total = query.count()

        collections = (
            query.order_by(Collection.position, Collection.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        results = []
        for c in collections:
            item_count = CollectionItem.select().where(CollectionItem.collection == c.id).count()
            child_count = (
                Collection.select()
                .where(
                    Collection.parent == c.id,
                    *_collection_scope_filters(Collection),
                )
                .count()
            )
            results.append(
                {
                    "collection_id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "item_count": item_count,
                    "child_collections": child_count,
                    "is_shared": c.is_shared,
                    "created_at": _isotime(c.created_at),
                    "updated_at": _isotime(c.updated_at),
                }
            )

        return json.dumps(
            {
                "collections": results,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("list_collections failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_collection(collection_id: int, include_items: bool = True, limit: int = 50) -> str:
    """Get details of a specific collection and its article summaries.

    Args:
        collection_id: The numeric ID of the collection.
        include_items: Whether to include the article summaries in the collection (default true).
        limit: Maximum articles to include (1-100, default 50).
    """
    from app.db.models import Collection, CollectionItem, Request, Summary

    limit = max(1, min(100, limit))

    try:
        collection = Collection.get_or_none(
            Collection.id == collection_id, *_collection_scope_filters(Collection)
        )
        if not collection:
            return json.dumps({"error": f"Collection {collection_id} not found"})

        # Child collections
        children = (
            Collection.select()
            .where(
                Collection.parent == collection.id,
                *_collection_scope_filters(Collection),
            )
            .order_by(Collection.position, Collection.created_at)
        )
        child_list = [
            {"collection_id": ch.id, "name": ch.name, "description": ch.description}
            for ch in children
        ]

        result: dict[str, Any] = {
            "collection_id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "is_shared": collection.is_shared,
            "child_collections": child_list,
            "created_at": _isotime(collection.created_at),
            "updated_at": _isotime(collection.updated_at),
        }

        if include_items:
            items = (
                CollectionItem.select(CollectionItem, Summary, Request)
                .join(Summary)
                .join(Request)
                .where(CollectionItem.collection == collection.id)
                .where(
                    Summary.is_deleted == False,  # noqa: E712
                    *_request_scope_filters(Request),
                )
                .order_by(CollectionItem.position, CollectionItem.created_at)
                .limit(limit)
            )
            articles = []
            for item in items:
                summary = item.summary
                articles.append(_format_summary_compact(summary, summary.request))
            result["articles"] = articles
            result["article_count"] = len(articles)

        return json.dumps(result, default=str)

    except Exception as exc:
        logger.exception("get_collection failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def list_videos(limit: int = 20, offset: int = 0, status: str | None = None) -> str:
    """List downloaded YouTube videos with metadata.

    Returns video downloads sorted most-recent first, with title,
    channel, duration, and transcript availability.

    Args:
        limit: Number of results (1-50, default 20).
        offset: Pagination offset (default 0).
        status: Optional filter by status: "completed", "pending", "error".
    """
    from app.db.models import Request, VideoDownload

    limit = max(1, min(50, limit))
    offset = max(0, offset)

    try:
        query = (
            VideoDownload.select(VideoDownload, Request)
            .join(Request)
            .where(*_request_scope_filters(Request))
        )

        if status and status in ("pending", "downloading", "completed", "error"):
            query = query.where(VideoDownload.status == status)

        total = query.count()
        videos = query.order_by(VideoDownload.created_at.desc()).offset(offset).limit(limit)

        results = []
        for v in videos:
            req = v.request
            results.append(
                {
                    "video_id": v.video_id,
                    "request_id": req.id,
                    "url": getattr(req, "input_url", ""),
                    "title": v.title,
                    "channel": v.channel,
                    "duration_sec": v.duration_sec,
                    "duration_display": (
                        f"{v.duration_sec // 60}:{v.duration_sec % 60:02d}"
                        if v.duration_sec
                        else None
                    ),
                    "resolution": v.resolution,
                    "view_count": v.view_count,
                    "like_count": v.like_count,
                    "has_transcript": bool(v.transcript_text),
                    "transcript_source": v.transcript_source,
                    "status": v.status,
                    "upload_date": v.upload_date,
                    "created_at": _isotime(v.created_at),
                }
            )

        return json.dumps(
            {
                "videos": results,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("list_videos failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_video_transcript(video_id: str) -> str:
    """Get the transcript text of a downloaded YouTube video.

    Returns the cached transcript text along with video metadata.
    The video_id is the YouTube video identifier (e.g. "dQw4w9WgXcQ").

    Args:
        video_id: YouTube video ID.
    """
    from app.db.models import Request, VideoDownload

    try:
        video = (
            VideoDownload.select(VideoDownload, Request)
            .join(Request)
            .where(VideoDownload.video_id == video_id, *_request_scope_filters(Request))
            .first()
        )
        if not video:
            return json.dumps({"error": f"Video {video_id} not found"})

        if not video.transcript_text:
            return json.dumps(
                {
                    "video_id": video_id,
                    "title": video.title,
                    "error": "No transcript available for this video",
                }
            )

        return json.dumps(
            {
                "video_id": video_id,
                "title": video.title,
                "channel": video.channel,
                "duration_sec": video.duration_sec,
                "transcript_source": video.transcript_source,
                "subtitle_language": video.subtitle_language,
                "auto_generated": video.auto_generated,
                "transcript": video.transcript_text[:50000],
                "transcript_length": len(video.transcript_text),
                "truncated": len(video.transcript_text) > 50000,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("get_video_transcript failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def check_url(url: str) -> str:
    """Check if a URL has already been processed and summarised.

    Uses the same normalisation and SHA-256 deduplication as the main
    pipeline.  Returns the existing summary if found, or an indication
    that the URL is new.

    Args:
        url: The URL to check (will be normalised automatically).
    """
    from app.core.url_utils import compute_dedupe_hash, normalize_url
    from app.db.models import Request, Summary

    try:
        normalized = normalize_url(url)
        dedupe_hash = compute_dedupe_hash(url)

        request = Request.get_or_none(
            Request.dedupe_hash == dedupe_hash, *_request_scope_filters(Request)
        )

        if not request:
            return json.dumps(
                {
                    "exists": False,
                    "normalized_url": normalized,
                    "dedupe_hash": dedupe_hash,
                    "message": "URL has not been processed yet",
                }
            )

        summary = (
            Summary.select()
            .where(
                Summary.request == request.id,
                Summary.is_deleted == False,  # noqa: E712
            )
            .first()
        )

        result: dict[str, Any] = {
            "exists": True,
            "normalized_url": normalized,
            "dedupe_hash": dedupe_hash,
            "request_id": request.id,
            "request_status": request.status,
            "request_type": request.type,
            "created_at": _isotime(request.created_at),
        }

        if summary:
            result["summary_id"] = summary.id
            result["summary"] = _format_summary_compact(summary, request)
        else:
            result["summary_id"] = None
            result["message"] = "URL was processed but no summary is available"

        return json.dumps(result, default=str)

    except Exception as exc:
        logger.exception("check_url failed")
        return json.dumps({"error": str(exc), "url": url})


@mcp.tool()
async def semantic_search(
    description: str,
    limit: int = 10,
    language: str | None = None,
    min_similarity: float = 0.25,
    rerank: bool = False,
    include_chunks: bool = True,
) -> str:
    """Search articles by semantic meaning with resilient fallback strategy."""
    try:
        payload = await _run_semantic_candidates(
            description,
            language=language,
            limit=limit,
            min_similarity=min_similarity,
            include_chunks=include_chunks,
            rerank=rerank,
            allow_keyword_fallback=True,
        )
        return json.dumps(
            {
                "results": payload.get("results", []),
                "total": len(payload.get("results", [])),
                "query": description,
                "search_type": payload.get("search_type", "semantic"),
                "search_backend": payload.get("search_backend", "none"),
                "has_more": bool(payload.get("has_more", False)),
                "min_similarity": round(_clamp_similarity(min_similarity), 4),
                "rerank_applied": bool(rerank),
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("semantic_search failed")
        return json.dumps({"error": str(exc), "query": description})


@mcp.tool()
async def hybrid_search(
    query: str,
    limit: int = 10,
    language: str | None = None,
    min_similarity: float = 0.25,
    rerank: bool = False,
) -> str:
    """Combine keyword and semantic retrieval into a single ranked result list."""
    limit = _clamp_limit(limit)

    try:
        semantic = await _run_semantic_candidates(
            query,
            language=language,
            limit=max(limit * 2, 12),
            min_similarity=min_similarity,
            include_chunks=True,
            rerank=rerank,
            allow_keyword_fallback=False,
        )
        semantic_results = semantic.get("results", [])
        if not isinstance(semantic_results, list):
            semantic_results = []

        keyword_payload = _ensure_mapping(search_articles(query=query, limit=max(limit * 2, 12)))
        keyword_results = keyword_payload.get("results", [])
        if not isinstance(keyword_results, list):
            keyword_results = []

        fused: dict[int, dict[str, Any]] = {}
        fusion_k = 50.0

        for idx, item in enumerate(semantic_results):
            summary_id = _safe_int(_ensure_mapping(item).get("summary_id"))
            if summary_id is None:
                continue
            bucket = fused.setdefault(summary_id, dict(item))
            bucket.setdefault("match_sources", [])
            if "semantic" not in bucket["match_sources"]:
                bucket["match_sources"].append("semantic")
            bucket["hybrid_score"] = float(bucket.get("hybrid_score", 0.0)) + (
                1.0 / (fusion_k + idx)
            )
            bucket["semantic_score"] = float(item.get("similarity_score", 0.0))

        for idx, item in enumerate(keyword_results):
            summary_id = _safe_int(_ensure_mapping(item).get("summary_id"))
            if summary_id is None:
                continue
            if summary_id not in fused:
                fused[summary_id] = dict(item)
                fused[summary_id]["semantic_score"] = None
            bucket = fused[summary_id]
            bucket.setdefault("match_sources", [])
            if "keyword" not in bucket["match_sources"]:
                bucket["match_sources"].append("keyword")
            bucket["hybrid_score"] = float(bucket.get("hybrid_score", 0.0)) + (
                1.0 / (fusion_k + idx)
            )

        results = sorted(
            fused.values(), key=lambda item: float(item.get("hybrid_score", 0.0)), reverse=True
        )
        for row in results:
            row["hybrid_score"] = round(float(row.get("hybrid_score", 0.0)), 4)

        return json.dumps(
            {
                "results": results[:limit],
                "total": min(len(results), limit),
                "query": query,
                "search_type": "hybrid",
                "semantic_backend": semantic.get("search_backend", "none"),
                "min_similarity": round(_clamp_similarity(min_similarity), 4),
                "rerank_applied": bool(rerank),
                "has_more": len(results) > limit,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("hybrid_search failed")
        return json.dumps({"error": str(exc), "query": query})


@mcp.tool()
async def find_similar_articles(
    summary_id: int,
    limit: int = 10,
    min_similarity: float = 0.3,
    rerank: bool = False,
    include_chunks: bool = True,
) -> str:
    """Find articles semantically similar to an existing summary."""
    from app.db.models import Request, Summary

    limit = _clamp_limit(limit)

    try:
        source_summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.id == summary_id,
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .get()
        )
    except Summary.DoesNotExist:
        return json.dumps({"error": f"Summary {summary_id} not found"})
    except Exception as exc:
        logger.exception("find_similar_articles source lookup failed")
        return json.dumps({"error": str(exc), "summary_id": summary_id})

    payload = _ensure_mapping(getattr(source_summary, "json_payload", None))
    seed_query = _extract_semantic_seed_text(payload)
    if not seed_query:
        return json.dumps(
            {
                "summary_id": summary_id,
                "results": [],
                "total": 0,
                "message": "Source summary has no text suitable for semantic search",
            }
        )

    try:
        semantic = await _run_semantic_candidates(
            seed_query,
            language=getattr(source_summary, "lang", None),
            limit=max(limit + 4, 12),
            min_similarity=min_similarity,
            include_chunks=include_chunks,
            rerank=rerank,
            allow_keyword_fallback=False,
        )
        raw_results = semantic.get("results", [])
        if not isinstance(raw_results, list):
            raw_results = []
        results = [
            row
            for row in raw_results
            if _safe_int(_ensure_mapping(row).get("summary_id")) != int(summary_id)
        ][:limit]

        return json.dumps(
            {
                "summary_id": summary_id,
                "query_seed": seed_query[:500],
                "results": results,
                "total": len(results),
                "search_type": "similarity",
                "search_backend": semantic.get("search_backend", "none"),
                "min_similarity": round(_clamp_similarity(min_similarity), 4),
                "rerank_applied": bool(rerank),
                "has_more": len(raw_results) > len(results),
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("find_similar_articles failed")
        return json.dumps({"error": str(exc), "summary_id": summary_id})


@mcp.tool()
async def chroma_health() -> str:
    """Check Chroma availability and fallback readiness."""
    try:
        chroma = await _get_chroma_service()
        local = await _get_local_vector_service()
        chroma_store = getattr(chroma, "_vector_store", None) if chroma else None

        now = time.monotonic()
        chroma_failed_for = (
            round(now - _chroma_last_failed_at, 2) if _chroma_last_failed_at is not None else None
        )
        local_failed_for = (
            round(now - _local_vector_last_failed_at, 2)
            if _local_vector_last_failed_at is not None
            else None
        )

        return json.dumps(
            {
                "chroma_available": bool(chroma is not None),
                "local_vector_available": bool(local is not None),
                "collection_name": getattr(chroma_store, "collection_name", None),
                "environment": getattr(chroma_store, "environment", None),
                "user_scope": getattr(chroma_store, "user_scope", None),
                "chroma_last_failed_seconds_ago": chroma_failed_for,
                "local_last_failed_seconds_ago": local_failed_for,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("chroma_health failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def chroma_index_stats(scan_limit: int = 5000) -> str:
    """Return index coverage stats between SQLite summaries and Chroma."""
    from app.db.models import Request, Summary

    scan_limit = max(100, min(50000, int(scan_limit)))

    try:
        chroma = await _get_chroma_service()
        if chroma is None:
            return json.dumps(
                {
                    "error": "ChromaDB unavailable",
                    "chroma_available": False,
                }
            )

        chroma_store = getattr(chroma, "_vector_store", None)
        if chroma_store is None:
            return json.dumps({"error": "Chroma store unavailable", "chroma_available": False})

        sqlite_query = (
            Summary.select(Summary.id, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
            .limit(scan_limit)
        )
        sqlite_ids = {int(row.id) for row in sqlite_query}

        chroma_ids = chroma_store.get_indexed_summary_ids(user_id=_MCP_USER_ID, limit=scan_limit)

        overlap = sqlite_ids.intersection(chroma_ids)
        coverage_pct = round((len(overlap) / len(sqlite_ids) * 100), 2) if sqlite_ids else 0.0

        return json.dumps(
            {
                "chroma_available": True,
                "user_scope_id": _MCP_USER_ID,
                "scan_limit": scan_limit,
                "sqlite_summary_count": len(sqlite_ids),
                "chroma_indexed_count": len(chroma_ids),
                "overlap_count": len(overlap),
                "coverage_percent": coverage_pct,
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("chroma_index_stats failed")
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def chroma_sync_gap(max_scan: int = 5000, sample_size: int = 20) -> str:
    """Report sync gaps between SQLite summaries and Chroma index."""
    from app.db.models import Request, Summary

    max_scan = max(100, min(50000, int(max_scan)))
    sample_size = max(1, min(100, int(sample_size)))

    try:
        chroma = await _get_chroma_service()
        if chroma is None:
            return json.dumps(
                {
                    "error": "ChromaDB unavailable",
                    "chroma_available": False,
                }
            )

        chroma_store = getattr(chroma, "_vector_store", None)
        if chroma_store is None:
            return json.dumps({"error": "Chroma store unavailable", "chroma_available": False})

        sqlite_query = (
            Summary.select(Summary.id, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
            .limit(max_scan)
        )
        sqlite_ids = {int(row.id) for row in sqlite_query}
        chroma_ids = chroma_store.get_indexed_summary_ids(user_id=_MCP_USER_ID, limit=max_scan)

        missing_in_chroma = sorted(sqlite_ids - chroma_ids)
        missing_in_sqlite = sorted(chroma_ids - sqlite_ids)

        return json.dumps(
            {
                "chroma_available": True,
                "user_scope_id": _MCP_USER_ID,
                "max_scan": max_scan,
                "sqlite_summary_count": len(sqlite_ids),
                "chroma_indexed_count": len(chroma_ids),
                "missing_in_chroma_count": len(missing_in_chroma),
                "missing_in_sqlite_count": len(missing_in_sqlite),
                "missing_in_chroma_sample": missing_in_chroma[:sample_size],
                "missing_in_sqlite_sample": missing_in_sqlite[:sample_size],
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("chroma_sync_gap failed")
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Resources — expose article database as discoverable resources
# ---------------------------------------------------------------------------
@mcp.resource("bsr://articles/recent")
def recent_articles_resource() -> str:
    """A snapshot of the 10 most recent article summaries."""
    return list_articles(limit=10, offset=0)


@mcp.resource("bsr://articles/favorites")
def favorites_resource() -> str:
    """All favorited article summaries."""
    return list_articles(limit=50, offset=0, is_favorited=True)


@mcp.resource("bsr://articles/unread")
def unread_resource() -> str:
    """Unread article summaries (up to 20)."""
    from app.db.models import Request, Summary

    try:
        summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                Summary.is_read == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
            .limit(20)
        )
        results = [_format_summary_compact(s, s.request) for s in summaries]
        return json.dumps({"articles": results, "total": len(results)}, default=str)
    except Exception as exc:
        logger.exception("unread_resource failed")
        return json.dumps({"error": str(exc)})


@mcp.resource("bsr://stats")
def stats_resource() -> str:
    """Current database statistics for Bite-Size Reader."""
    return get_stats()


@mcp.resource("bsr://tags")
def tags_resource() -> str:
    """All topic tags with article counts, sorted by frequency."""
    from app.db.models import Request, Summary

    try:
        tag_counts: dict[str, int] = {}
        all_summaries = (
            Summary.select(Summary.json_payload, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
        )
        for row in all_summaries:
            payload = _ensure_mapping(getattr(row, "json_payload", None))
            for tag in payload.get("topic_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        return json.dumps(
            {
                "tags": [{"tag": t, "count": c} for t, c in sorted_tags],
                "total_unique_tags": len(sorted_tags),
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("tags_resource failed")
        return json.dumps({"error": str(exc)})


@mcp.resource("bsr://entities")
def entities_resource() -> str:
    """Aggregated entities (people, organizations, locations) across all articles."""
    from app.db.models import Request, Summary

    try:
        people: dict[str, int] = {}
        orgs: dict[str, int] = {}
        locations: dict[str, int] = {}

        all_summaries = (
            Summary.select(Summary.json_payload, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
            .order_by(Summary.created_at.desc())
        )
        for row in all_summaries:
            payload = _ensure_mapping(getattr(row, "json_payload", None))
            entities = _ensure_mapping(payload.get("entities"))
            for p in entities.get("people", []):
                people[p] = people.get(p, 0) + 1
            for o in entities.get("organizations", []):
                orgs[o] = orgs.get(o, 0) + 1
            for loc in entities.get("locations", []):
                locations[loc] = locations.get(loc, 0) + 1

        def _top(d: dict[str, int], n: int = 50) -> list[dict]:
            return [
                {"name": k, "count": v}
                for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]
            ]

        return json.dumps(
            {
                "people": _top(people),
                "organizations": _top(orgs),
                "locations": _top(locations),
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("entities_resource failed")
        return json.dumps({"error": str(exc)})


@mcp.resource("bsr://domains")
def domains_resource() -> str:
    """Source domains with article counts, sorted by frequency."""
    from app.db.models import Request, Summary

    try:
        domain_counts: dict[str, int] = {}
        all_summaries = (
            Summary.select(Summary.json_payload, Request)
            .join(Request)
            .where(
                Summary.is_deleted == False,  # noqa: E712
                *_request_scope_filters(Request),
            )
        )
        for row in all_summaries:
            payload = _ensure_mapping(getattr(row, "json_payload", None))
            metadata = _ensure_mapping(payload.get("metadata"))
            domain = metadata.get("domain", "")
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

        sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
        return json.dumps(
            {
                "domains": [{"domain": d, "count": c} for d, c in sorted_domains],
                "total_unique_domains": len(sorted_domains),
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("domains_resource failed")
        return json.dumps({"error": str(exc)})


@mcp.resource("bsr://collections")
def collections_resource() -> str:
    """All top-level collections with item counts."""
    return list_collections(limit=50, offset=0)


@mcp.resource("bsr://videos/recent")
def recent_videos_resource() -> str:
    """10 most recent video downloads with metadata."""
    return list_videos(limit=10, offset=0, status="completed")


@mcp.resource("bsr://processing/stats")
def processing_stats_resource() -> str:
    """Processing statistics: LLM call counts, token usage, model breakdown."""
    from app.db.models import LLMCall, Request, VideoDownload

    try:
        llm_scope_filters = [LLMCall.is_deleted == False, *_request_scope_filters(Request)]  # noqa: E712

        total_calls = LLMCall.select(LLMCall.id).join(Request).where(*llm_scope_filters).count()
        success_calls = (
            LLMCall.select(LLMCall.id)
            .join(Request)
            .where(*llm_scope_filters, LLMCall.status == "success")
            .count()
        )
        error_calls = (
            LLMCall.select(LLMCall.id)
            .join(Request)
            .where(*llm_scope_filters, LLMCall.status == "error")
            .count()
        )

        # Token usage
        from peewee import fn

        token_stats = (
            LLMCall.select(
                fn.SUM(LLMCall.tokens_prompt).alias("total_prompt"),
                fn.SUM(LLMCall.tokens_completion).alias("total_completion"),
                fn.SUM(LLMCall.cost_usd).alias("total_cost"),
                fn.AVG(LLMCall.latency_ms).alias("avg_latency_ms"),
            )
            .join(Request)
            .where(*llm_scope_filters, LLMCall.status == "success")
            .dicts()
            .first()
        ) or {}

        # Model breakdown
        model_counts: dict[str, int] = {}
        for row in (
            LLMCall.select(LLMCall.model)
            .join(Request)
            .where(*llm_scope_filters, LLMCall.status == "success", LLMCall.model.is_null(False))
            .dicts()
        ):
            model = row.get("model") or "unknown"
            model_counts[model] = model_counts.get(model, 0) + 1

        top_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Video stats
        video_base = (
            VideoDownload.select(VideoDownload.id)
            .join(Request)
            .where(*_request_scope_filters(Request))
        )

        total_videos = video_base.count()
        completed_videos = video_base.where(VideoDownload.status == "completed").count()
        videos_with_transcript = video_base.where(
            VideoDownload.status == "completed",
            VideoDownload.transcript_text.is_null(False),
        ).count()

        return json.dumps(
            {
                "llm_calls": {
                    "total": total_calls,
                    "success": success_calls,
                    "errors": error_calls,
                    "success_rate": (
                        round(success_calls / total_calls * 100, 1) if total_calls > 0 else 0
                    ),
                },
                "token_usage": {
                    "total_prompt_tokens": token_stats.get("total_prompt"),
                    "total_completion_tokens": token_stats.get("total_completion"),
                    "total_cost_usd": (
                        round(float(token_stats["total_cost"]), 4)
                        if token_stats.get("total_cost")
                        else None
                    ),
                    "avg_latency_ms": (
                        round(float(token_stats["avg_latency_ms"]))
                        if token_stats.get("avg_latency_ms")
                        else None
                    ),
                },
                "top_models": [{"model": m, "calls": c} for m, c in top_models],
                "videos": {
                    "total": total_videos,
                    "completed": completed_videos,
                    "with_transcript": videos_with_transcript,
                },
            },
            default=str,
        )
    except Exception as exc:
        logger.exception("processing_stats_resource failed")
        return json.dumps({"error": str(exc)})


@mcp.resource("bsr://chroma/health")
def chroma_health_resource() -> str:
    """Chroma availability status for semantic MCP tools."""
    return _run_async_for_resource(chroma_health())


@mcp.resource("bsr://chroma/index-stats")
def chroma_index_stats_resource() -> str:
    """Chroma index coverage compared to SQLite summaries."""
    return _run_async_for_resource(chroma_index_stats())


@mcp.resource("bsr://chroma/sync-gap")
def chroma_sync_gap_resource() -> str:
    """Chroma/SQLite sync gap sample using default scan limits."""
    return _run_async_for_resource(chroma_sync_gap())


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------
def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8200,
    db_path: str | None = None,
    user_id: int | None = None,
    allow_remote_sse: bool = False,
    allow_unscoped_sse: bool = False,
) -> None:
    """Start the MCP server.

    Args:
        transport: "stdio" (default) or "sse".
        host: Bind address for SSE transport (default 127.0.0.1).
        port: Port for SSE transport (default 8200).
        db_path: Override for database file path.
        user_id: Optional user scope. When set, all MCP reads are scoped to this user.
        allow_remote_sse: Allow non-loopback SSE bind host.
        allow_unscoped_sse: Allow SSE without explicit user scoping.
    """
    _init_database(db_path)
    _set_user_scope(user_id)
    logger.info(
        "Starting Bite-Size Reader MCP server (transport=%s, user_scope=%s)",
        transport,
        user_id if user_id is not None else "all",
    )

    if transport == "sse" and not allow_remote_sse and not _is_loopback_host(host):
        msg = (
            "Refusing to bind MCP SSE to non-loopback host without explicit opt-in "
            "(set allow_remote_sse=True / --allow-remote-sse)."
        )
        raise ValueError(msg)

    if transport == "sse" and user_id is None and not allow_unscoped_sse:
        msg = (
            "Refusing to start unscoped MCP SSE server. Set MCP_USER_ID/--user-id or "
            "explicitly acknowledge risk via allow_unscoped_sse=True / --allow-unscoped-sse."
        )
        raise ValueError(msg)

    if user_id is None:
        logger.warning("MCP user scope is disabled; queries can access all users")

    if transport == "sse":
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
