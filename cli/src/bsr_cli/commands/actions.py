"""Simple action commands -- delete, favorite, read."""

from __future__ import annotations

import click
from bsr_cli.auth import get_client
from bsr_cli.output import echo_success, format_json


@click.command()
@click.argument("id", type=int)
@click.pass_context
def delete(ctx: click.Context, id: int) -> None:
    """Delete a summary by ID."""
    client = get_client(ctx.obj)
    client.delete_summary(id)
    if ctx.obj["json"]:
        format_json({"deleted": id})
    else:
        echo_success(f"Deleted summary {id}")


@click.command()
@click.argument("id", type=int)
@click.pass_context
def favorite(ctx: click.Context, id: int) -> None:
    """Toggle favorite on a summary."""
    client = get_client(ctx.obj)
    result = client.toggle_favorite(id)
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Toggled favorite for summary {id}")


@click.command("read")
@click.argument("id", type=int)
@click.pass_context
def read_cmd(ctx: click.Context, id: int) -> None:
    """Mark a summary as read."""
    client = get_client(ctx.obj)
    result = client.mark_read(id)
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Marked summary {id} as read")
