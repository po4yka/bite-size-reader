"""CLI entry point for the Bite-Size Reader MCP server.

Starts an MCP (Model Context Protocol) server that exposes articles
and search functionality to external AI agents like OpenClaw.

Usage:
    # stdio transport (default — for OpenClaw, Claude Desktop, etc.)
    python -m app.cli.mcp_server

    # SSE transport (local-only by default, requires user scope)
    python -m app.cli.mcp_server --transport sse --user-id 12345

    # Custom database path
    python -m app.cli.mcp_server --db-path /path/to/app.db
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bsr-mcp-server",
        description="Bite-Size Reader MCP server for AI agent integrations",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="Transport protocol (defaults to MCP_TRANSPORT or 'stdio')",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind address for SSE transport (defaults to MCP_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for SSE transport (defaults to MCP_PORT or 8200)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override path to SQLite database file",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Scope MCP reads to a single user ID (or use MCP_USER_ID)",
    )
    parser.add_argument(
        "--allow-remote-sse",
        action="store_true",
        help="Allow SSE bind on non-loopback hosts (unsafe by default)",
    )
    parser.add_argument(
        "--allow-unscoped-sse",
        action="store_true",
        help="Allow SSE without --user-id / MCP_USER_ID (unsafe by default)",
    )

    args = parser.parse_args()

    import logging

    from app.config.integrations import McpConfig

    cfg = McpConfig.model_validate(dict(os.environ))
    transport = args.transport or cfg.transport
    host = args.host or cfg.host
    port = args.port if args.port is not None else cfg.port
    user_id = args.user_id if args.user_id is not None else cfg.user_id
    allow_remote_sse = args.allow_remote_sse or cfg.allow_remote_sse
    allow_unscoped_sse = args.allow_unscoped_sse or cfg.allow_unscoped_sse

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from app.mcp.server import run_server

    run_server(
        transport=transport,
        host=host,
        port=port,
        db_path=args.db_path,
        user_id=user_id,
        allow_remote_sse=allow_remote_sse,
        allow_unscoped_sse=allow_unscoped_sse,
    )


if __name__ == "__main__":
    main()
