"""Search command -- search summaries."""

from __future__ import annotations

import click
from ratatoskr_cli.auth import get_client
from ratatoskr_cli.output import format_search_results


@click.command()
@click.argument("query")
@click.option("--limit", "-n", default=20)
@click.option("--tag", "-t", multiple=True)
@click.option("--lang", type=click.Choice(["en", "ru"]))
@click.option("--domain", "-d", multiple=True)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    limit: int,
    tag: tuple[str, ...],
    lang: str | None,
    domain: tuple[str, ...],
) -> None:
    """Search summaries."""
    client = get_client(ctx.obj)
    result = client.search(
        query,
        limit=limit,
        language=lang,
        tags=list(tag) or None,
        domains=list(domain) or None,
    )
    format_search_results(result, ctx.obj["json"])
