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
    python -m app.cli.mcp_server --transport sse --port 8200
"""

from __future__ import annotations

import json
import logging
import os
import sys
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
_chroma_init_attempted: bool = False


async def _get_chroma_service() -> Any:
    """Lazily initialise and return the ChromaVectorSearchService singleton.

    Returns None if ChromaDB is unavailable (the semantic_search tool
    will degrade to a helpful error message).
    """
    global _chroma_service, _chroma_init_attempted

    if _chroma_service is not None:
        return _chroma_service
    if _chroma_init_attempted:
        return None

    _chroma_init_attempted = True
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
        logger.info("ChromaDB search service initialised")
        return _chroma_service
    except Exception:
        logger.warning(
            "ChromaDB unavailable — semantic_search tool will be disabled",
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
    if hasattr(dt, "isoformat"):
        return dt.isoformat() + "Z"
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

        request_ids = [r["request_id"] for r in fts_list if r.get("request_id")]
        if not request_ids:
            return json.dumps({"results": [], "total": 0, "query": query})

        # Load summaries for matched requests
        summaries = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(
                Request.id.in_(request_ids),
                Summary.is_deleted == False,  # noqa: E712
            )
            .order_by(Summary.created_at.desc())
        )

        results = []
        for s in summaries:
            req = s.request
            results.append(_format_summary_compact(s, req))

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
        .where(Summary.is_deleted == False)  # noqa: E712
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
            Summary.select(Summary, Request).join(Request).where(Summary.is_deleted == False)  # noqa: E712
        )

        if is_favorited is not None:
            query = query.where(Summary.is_favorited == is_favorited)

        if lang:
            query = query.where(Summary.lang == lang)

        # Count total before pagination
        total = query.count()

        articles = query.order_by(Summary.created_at.desc()).offset(offset).limit(limit)

        results = []
        for s in articles:
            compact = _format_summary_compact(s, s.request)

            # Apply tag filter client-side (tags are in JSON payload)
            if tag:
                tag_normalized = tag if tag.startswith("#") else f"#{tag}"
                tags = compact.get("topic_tags", [])
                if tag_normalized.lower() not in [t.lower() for t in tags]:
                    total -= 1
                    continue

            results.append(compact)

        return json.dumps(
            {
                "articles": results,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
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
            )
            .get()
        )

        request = summary.request
        crawl = CrawlResult.select().where(CrawlResult.request == request.id).first()

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
        total = Summary.select().where(Summary.is_deleted == False).count()  # noqa: E712
        unread = (
            Summary.select()
            .where(
                Summary.is_deleted == False,  # noqa: E712
                Summary.is_read == False,  # noqa: E712
            )
            .count()
        )
        favorited = (
            Summary.select()
            .where(
                Summary.is_deleted == False,  # noqa: E712
                Summary.is_favorited == True,  # noqa: E712
            )
            .count()
        )

        # Language breakdown
        lang_counts: dict[str, int] = {}
        for row in (
            Summary.select(Summary.lang).where(Summary.is_deleted == False).dicts()  # noqa: E712
        ):
            lang = row.get("lang") or "unknown"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        # Top tags (sample recent 200 summaries)
        tag_counts: dict[str, int] = {}
        recent = (
            Summary.select(Summary.json_payload)
            .where(Summary.is_deleted == False)  # noqa: E712
            .order_by(Summary.created_at.desc())
            .limit(200)
        )
        for row in recent:
            payload = _ensure_mapping(getattr(row, "json_payload", None))
            for tag in payload.get("topic_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        # Request type breakdown
        url_count = Request.select().where(Request.type == "url").count()
        forward_count = Request.select().where(Request.type == "forward").count()

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
            .where(Summary.is_deleted == False)  # noqa: E712
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
            Collection.is_deleted == False,  # noqa: E712
            Collection.parent.is_null(True),
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
                    Collection.is_deleted == False,  # noqa: E712
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
            Collection.id == collection_id,
            Collection.is_deleted == False,  # noqa: E712
        )
        if not collection:
            return json.dumps({"error": f"Collection {collection_id} not found"})

        # Child collections
        children = (
            Collection.select()
            .where(
                Collection.parent == collection.id,
                Collection.is_deleted == False,  # noqa: E712
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
        query = VideoDownload.select(VideoDownload, Request).join(Request)

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
            .where(VideoDownload.video_id == video_id)
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

        request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)

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
) -> str:
    """Search articles by meaning using vector similarity (ChromaDB).

    Unlike keyword search, this finds articles whose *content* is
    semantically similar to your description — even when exact keywords
    don't match. Use this when you want to find articles "about" a topic
    described in natural language.

    Requires ChromaDB to be configured and running. Falls back to
    keyword search if ChromaDB is unavailable.

    Args:
        description: Natural-language description of what you're looking for
                     (e.g. "articles about climate change policy in Europe").
        limit: Maximum number of results to return (1-25, default 10).
        language: Optional language filter (e.g. "en", "ru"). Auto-detected if omitted.
    """
    limit = max(1, min(25, limit))

    chroma = await _get_chroma_service()

    if chroma is None:
        # Graceful degradation: fall back to keyword search
        logger.info("semantic_search: ChromaDB unavailable, falling back to keyword search")
        return search_articles(query=description, limit=limit)

    try:
        results = await chroma.search(
            description.strip(),
            language=language,
            limit=limit,
            offset=0,
        )

        # Enrich Chroma results with full summary data from SQLite
        from app.db.models import Request, Summary

        output = []
        for r in results.results:
            try:
                summary = (
                    Summary.select(Summary, Request)
                    .join(Request)
                    .where(
                        Summary.id == r.summary_id,
                        Summary.is_deleted == False,  # noqa: E712
                    )
                    .get()
                )
                compact = _format_summary_compact(summary, summary.request)
                compact["similarity_score"] = round(r.similarity_score, 4)
                output.append(compact)
            except Summary.DoesNotExist:
                # Chroma entry with no matching summary — skip
                continue

        return json.dumps(
            {
                "results": output,
                "total": len(output),
                "query": description,
                "search_type": "semantic",
                "has_more": results.has_more,
            },
            default=str,
        )

    except Exception as exc:
        logger.exception("semantic_search failed")
        return json.dumps({"error": str(exc), "query": description})


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
    from app.db.models import Summary

    try:
        tag_counts: dict[str, int] = {}
        all_summaries = (
            Summary.select(Summary.json_payload)
            .where(Summary.is_deleted == False)  # noqa: E712
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
    from app.db.models import Summary

    try:
        people: dict[str, int] = {}
        orgs: dict[str, int] = {}
        locations: dict[str, int] = {}

        all_summaries = (
            Summary.select(Summary.json_payload)
            .where(Summary.is_deleted == False)  # noqa: E712
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
            .where(Summary.is_deleted == False)  # noqa: E712
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
    from app.db.models import LLMCall, VideoDownload

    try:
        total_calls = LLMCall.select().count()
        success_calls = LLMCall.select().where(LLMCall.status == "success").count()
        error_calls = LLMCall.select().where(LLMCall.status == "error").count()

        # Token usage
        from peewee import fn

        token_stats = (
            LLMCall.select(
                fn.SUM(LLMCall.tokens_prompt).alias("total_prompt"),
                fn.SUM(LLMCall.tokens_completion).alias("total_completion"),
                fn.SUM(LLMCall.cost_usd).alias("total_cost"),
                fn.AVG(LLMCall.latency_ms).alias("avg_latency_ms"),
            )
            .where(LLMCall.status == "success")
            .dicts()
            .first()
        ) or {}

        # Model breakdown
        model_counts: dict[str, int] = {}
        for row in (
            LLMCall.select(LLMCall.model)
            .where(LLMCall.status == "success", LLMCall.model.is_null(False))
            .dicts()
        ):
            model = row.get("model") or "unknown"
            model_counts[model] = model_counts.get(model, 0) + 1

        top_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Video stats
        total_videos = VideoDownload.select().count()
        completed_videos = VideoDownload.select().where(VideoDownload.status == "completed").count()
        videos_with_transcript = (
            VideoDownload.select()
            .where(
                VideoDownload.status == "completed",
                VideoDownload.transcript_text.is_null(False),
            )
            .count()
        )

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


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------
def run_server(
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8200,
    db_path: str | None = None,
) -> None:
    """Start the MCP server.

    Args:
        transport: "stdio" (default) or "sse".
        host: Bind address for SSE transport (default 0.0.0.0).
        port: Port for SSE transport (default 8200).
        db_path: Override for database file path.
    """
    _init_database(db_path)
    logger.info("Starting Bite-Size Reader MCP server (transport=%s)", transport)

    if transport == "sse":
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
