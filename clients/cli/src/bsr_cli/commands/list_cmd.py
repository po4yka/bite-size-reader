"""List command -- list saved summaries."""

from __future__ import annotations

import click
from bsr_cli.auth import get_client
from bsr_cli.output import format_summary_list


@click.command("list")
@click.option("--limit", "-n", default=20, help="Results per page")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--unread", is_flag=True, help="Only unread")
@click.option("--favorites", is_flag=True, help="Only favorites")
@click.option("--tag", "-t", help="Filter by tag name")
@click.pass_context
def list_cmd(
    ctx: click.Context, limit: int, offset: int, unread: bool, favorites: bool, tag: str | None
) -> None:
    """List saved summaries."""
    client = get_client(ctx.obj)
    is_read = False if unread else None
    is_fav = True if favorites else None
    result = client.list_summaries(
        limit=limit, offset=offset, is_read=is_read, is_favorited=is_fav, tag=tag
    )
    format_summary_list(result, ctx.obj["json"])
