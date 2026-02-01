"""CLI entry point for the Bite-Size Reader MCP server.

Starts an MCP (Model Context Protocol) server that exposes articles
and search functionality to external AI agents like OpenClaw.

Usage:
    # stdio transport (default — for OpenClaw, Claude Desktop, etc.)
    python -m app.cli.mcp_server

    # SSE transport (for HTTP-based integrations)
    python -m app.cli.mcp_server --transport sse --port 8200

    # Custom database path
    python -m app.cli.mcp_server --db-path /path/to/app.db
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bsr-mcp-server",
        description="Bite-Size Reader MCP server for AI agent integrations",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8200,
        help="Port for SSE transport (default: 8200)",
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

    args = parser.parse_args()

    import logging

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from app.mcp.server import run_server

    run_server(
        transport=args.transport,
        host=args.host,
        port=args.port,
        db_path=args.db_path,
    )


if __name__ == "__main__":
    main()
