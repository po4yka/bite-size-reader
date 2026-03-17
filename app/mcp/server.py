"""MCP server entrypoint and FastMCP composition shell."""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from app.mcp.article_service import ArticleReadService
from app.mcp.catalog_service import CatalogReadService
from app.mcp.context import McpServerContext
from app.mcp.resource_registrations import register_resources
from app.mcp.semantic_service import SemanticSearchService
from app.mcp.tool_registrations import register_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("bsr.mcp")

_DEFAULT_CONTEXT = McpServerContext(logger=logger)


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def create_mcp_server(context: McpServerContext | None = None) -> FastMCP:
    server_context = context or _DEFAULT_CONTEXT
    mcp = FastMCP(
        "bite-size-reader",
        instructions=(
            "Bite-Size Reader is a personal knowledge base of web article summaries. "
            "Use the tools below to search, retrieve, and explore stored articles. "
            "Articles are summarised with key ideas, topic tags, entities, "
            "reading-time estimates, and more."
        ),
    )

    article_service = ArticleReadService(server_context)
    catalog_service = CatalogReadService(server_context)
    semantic_service = SemanticSearchService(server_context, article_service)

    register_tools(
        mcp,
        article_service=article_service,
        catalog_service=catalog_service,
        semantic_service=semantic_service,
    )
    register_resources(
        mcp,
        article_service=article_service,
        catalog_service=catalog_service,
        semantic_service=semantic_service,
    )
    return mcp


mcp = create_mcp_server()


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8200,
    db_path: str | None = None,
    user_id: int | None = None,
    allow_remote_sse: bool = False,
    allow_unscoped_sse: bool = False,
) -> None:
    """Start the MCP server."""
    _DEFAULT_CONTEXT.set_user_scope(user_id)
    _DEFAULT_CONTEXT.init_runtime(db_path)
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
