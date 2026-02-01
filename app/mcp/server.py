"""MCP server exposing Bite-Size Reader articles and search to AI agents.

This module implements a Model Context Protocol (MCP) server that allows
external AI agents (OpenClaw, Claude Desktop, etc.) to:
- Search stored article summaries by keyword, topic, or entity
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


# ---------------------------------------------------------------------------
# MCP Resources — expose article database as a discoverable resource
# ---------------------------------------------------------------------------
@mcp.resource("bsr://articles/recent")
def recent_articles_resource() -> str:
    """A snapshot of the 10 most recent article summaries."""
    return list_articles(limit=10, offset=0)


@mcp.resource("bsr://stats")
def stats_resource() -> str:
    """Current database statistics for Bite-Size Reader."""
    return get_stats()


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
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")
