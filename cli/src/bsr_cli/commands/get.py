"""Get command -- get summary details by ID."""

from __future__ import annotations

import click
from bsr_cli.auth import get_client
from bsr_cli.output import format_summary_detail


@click.command()
@click.argument("id", type=int)
@click.option("--content", is_flag=True, help="Include full article content")
@click.pass_context
def get(ctx: click.Context, id: int, content: bool) -> None:
    """Get summary details by ID."""
    client = get_client(ctx.obj)
    result = client.get_summary(id)
    if content:
        content_data = client.get_summary_content(id)
        result["content"] = content_data
    format_summary_detail(result, ctx.obj["json"])
