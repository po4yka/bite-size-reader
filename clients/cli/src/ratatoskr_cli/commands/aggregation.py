"""Aggregation CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from ratatoskr_cli.auth import get_client
from ratatoskr_cli.output import format_aggregation_detail, format_aggregation_list

AGGREGATION_HINT_CHOICES = [
    "x_post",
    "x_article",
    "threads_post",
    "instagram_post",
    "instagram_carousel",
    "instagram_reel",
    "web_article",
    "telegram_post",
    "youtube_video",
]


def _read_urls_from_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        urls.append(value)
    return urls


def _collect_urls(urls: tuple[str, ...], source_file: str | None) -> list[str]:
    collected = [url.strip() for url in urls if url.strip()]
    if source_file:
        collected.extend(_read_urls_from_file(Path(source_file)))
    return collected


def _build_items(urls: list[str], hints: tuple[str, ...]) -> list[dict[str, str]]:
    if len(hints) > len(urls):
        raise click.UsageError("Number of --hint values cannot exceed the submitted URLs")

    items: list[dict[str, str]] = []
    for index, url in enumerate(urls):
        item: dict[str, str] = {"type": "url", "url": url}
        if index < len(hints):
            hint = hints[index].strip()
            if hint:
                item["source_kind_hint"] = hint
        items.append(item)
    return items


@click.command("aggregate")
@click.argument("urls", nargs=-1)
@click.option(
    "--file",
    "source_file",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Read URLs from a file, one per line",
)
@click.option(
    "--lang",
    type=click.Choice(["auto", "en", "ru"]),
    default="auto",
    show_default=True,
    help="Preferred language",
)
@click.option(
    "--hint",
    multiple=True,
    type=click.Choice(AGGREGATION_HINT_CHOICES),
    help="Source-kind hint for the matching URL",
)
@click.pass_context
def aggregate(
    ctx: click.Context,
    urls: tuple[str, ...],
    source_file: str | None,
    lang: str,
    hint: tuple[str, ...],
) -> None:
    """Submit a mixed-source aggregation bundle.

    Examples:
      ratatoskr aggregate https://x.com/... https://youtube.com/...
      ratatoskr aggregate --file sources.txt --lang en
    """
    client = get_client(ctx.obj)
    collected_urls = _collect_urls(urls, source_file)
    if not collected_urls:
        raise click.UsageError("Provide at least one URL or --file with URLs")

    items = _build_items(collected_urls, hint)
    result = client.create_aggregation_bundle(items, lang_preference=lang)
    format_aggregation_detail(result, ctx.obj["json"])


@click.group(invoke_without_command=True)
@click.pass_context
def aggregation(ctx: click.Context) -> None:
    """Inspect aggregation sessions."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@aggregation.command("get")
@click.argument("session_id", type=int)
@click.pass_context
def aggregation_get(ctx: click.Context, session_id: int) -> None:
    """Get one aggregation session by ID."""
    client = get_client(ctx.obj)
    result = client.get_aggregation_bundle(session_id)
    format_aggregation_detail(result, ctx.obj["json"])


@aggregation.command("list")
@click.option("--limit", "-n", default=20, show_default=True, help="Results per page")
@click.option("--offset", default=0, show_default=True, help="Pagination offset")
@click.pass_context
def aggregation_list(ctx: click.Context, limit: int, offset: int) -> None:
    """List aggregation sessions."""
    client = get_client(ctx.obj)
    result = client.list_aggregation_bundles(limit=limit, offset=offset)
    format_aggregation_list(result, ctx.obj["json"])
