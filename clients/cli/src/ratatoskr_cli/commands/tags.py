"""Ratatoskr CLI tag management commands."""

from __future__ import annotations

import click
from ratatoskr_cli.auth import get_client
from ratatoskr_cli.output import echo_success, format_json, format_tags


@click.group(invoke_without_command=True)
@click.pass_context
def tags(ctx: click.Context) -> None:
    """Manage tags."""
    if ctx.invoked_subcommand is None:
        # Default: list tags
        client = get_client(ctx.obj)
        result = client.list_tags()
        format_tags(result, ctx.obj["json"])


@tags.command("create")
@click.argument("name")
@click.option("--color", help="Hex color (e.g., #3B82F6)")
@click.pass_context
def tags_create(ctx: click.Context, name: str, color: str | None) -> None:
    """Create a new tag."""
    client = get_client(ctx.obj)
    result = client.create_tag(name, color=color)
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Tag created: {result.get('name')} (id={result.get('id')})")


@tags.command("delete")
@click.argument("tag_id", type=int)
@click.confirmation_option(prompt="Delete this tag?")
@click.pass_context
def tags_delete(ctx: click.Context, tag_id: int) -> None:
    """Delete a tag."""
    client = get_client(ctx.obj)
    client.delete_tag(tag_id)
    echo_success(f"Tag {tag_id} deleted.")


@tags.command("attach")
@click.argument("summary_id", type=int)
@click.argument("tag_name")
@click.pass_context
def tags_attach(ctx: click.Context, summary_id: int, tag_name: str) -> None:
    """Attach a tag to a summary."""
    client = get_client(ctx.obj)
    result = client.attach_tags(summary_id, [tag_name])
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Tag '{tag_name}' attached to summary {summary_id}.")


@tags.command("detach")
@click.argument("summary_id", type=int)
@click.argument("tag_id", type=int)
@click.pass_context
def tags_detach(ctx: click.Context, summary_id: int, tag_id: int) -> None:
    """Detach a tag from a summary."""
    client = get_client(ctx.obj)
    client.detach_tag(summary_id, tag_id)
    echo_success(f"Tag {tag_id} detached from summary {summary_id}.")
