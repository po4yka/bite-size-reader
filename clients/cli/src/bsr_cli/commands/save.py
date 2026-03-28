"""Save command -- save a URL to Bite-Size Reader."""

from __future__ import annotations

import click
from bsr_cli.auth import get_client
from bsr_cli.output import echo_success, format_json


@click.command()
@click.argument("url")
@click.option("--title", "-T", help="Custom title")
@click.option("--tag", "-t", multiple=True, help="Tags (repeatable)")
@click.option("--summarize/--no-summarize", default=True, help="Trigger summarization")
@click.option("--note", help="Note / selected text")
@click.pass_context
def save(
    ctx: click.Context,
    url: str,
    title: str | None,
    tag: tuple[str, ...],
    summarize: bool,
    note: str | None,
) -> None:
    """Save a URL to Bite-Size Reader."""
    client = get_client(ctx.obj)
    result = client.quick_save(
        url,
        title=title,
        tag_names=list(tag) or None,
        summarize=summarize,
        selected_text=note,
    )
    if ctx.obj["json"]:
        format_json(result)
    else:
        dup = result.get("duplicate", False)
        if dup:
            echo_success(f"Already saved (id={result.get('request_id')})")
        else:
            echo_success(f"Saved! Request ID: {result.get('request_id')}")
            if result.get("tags_attached"):
                click.echo(f"Tags: {', '.join(result['tags_attached'])}")
