"""Ratatoskr CLI collection management commands."""

from __future__ import annotations

import click
from ratatoskr_cli.auth import get_client
from ratatoskr_cli.output import echo_success, format_collections, format_json


@click.group(invoke_without_command=True)
@click.pass_context
def collections(ctx: click.Context) -> None:
    """Manage collections."""
    if ctx.invoked_subcommand is None:
        client = get_client(ctx.obj)
        result = client.list_collections()
        format_collections(result, ctx.obj["json"])


@collections.command("create")
@click.argument("name")
@click.option("--description", "-d", help="Collection description")
@click.pass_context
def collections_create(ctx: click.Context, name: str, description: str | None) -> None:
    """Create a new collection."""
    client = get_client(ctx.obj)
    result = client.create_collection(name, description=description)
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Collection created: {result.get('name')} (id={result.get('id')})")


@collections.command("delete")
@click.argument("collection_id", type=int)
@click.confirmation_option(prompt="Delete this collection?")
@click.pass_context
def collections_delete(ctx: click.Context, collection_id: int) -> None:
    """Delete a collection."""
    client = get_client(ctx.obj)
    client.delete_collection(collection_id)
    echo_success(f"Collection {collection_id} deleted.")


@collections.command("add")
@click.argument("collection_id", type=int)
@click.argument("summary_id", type=int)
@click.pass_context
def collections_add(ctx: click.Context, collection_id: int, summary_id: int) -> None:
    """Add a summary to a collection."""
    client = get_client(ctx.obj)
    result = client.add_to_collection(collection_id, summary_id)
    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Summary {summary_id} added to collection {collection_id}.")
