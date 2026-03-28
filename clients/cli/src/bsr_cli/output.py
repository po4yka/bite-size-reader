"""BSR CLI output formatters."""

from __future__ import annotations

import json
from typing import Any

import click


def format_json(data: Any) -> None:
    """Output raw JSON."""
    click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def format_summary_list(data: Any, json_mode: bool = False) -> None:
    """Format a list of summaries."""
    if json_mode:
        format_json(data)
        return

    summaries = data if isinstance(data, list) else data.get("summaries", [])
    if not summaries:
        click.echo("No summaries found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Summaries")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", max_width=50)
        table.add_column("Domain", max_width=25)
        table.add_column("Read", width=4)
        table.add_column("Fav", width=4)
        table.add_column("Date", width=12)

        for s in summaries:
            sid = str(s.get("id", ""))
            title = (s.get("title") or s.get("url", ""))[:50]
            domain = (s.get("domain") or "")[:25]
            read = "Y" if s.get("isRead") or s.get("is_read") else ""
            fav = "*" if s.get("isFavorited") or s.get("is_favorited") else ""
            date = (s.get("createdAt") or s.get("created_at", ""))[:10]
            table.add_row(sid, title, domain, read, fav, date)

        console.print(table)
    except ImportError:
        # Fallback: plain text
        for s in summaries:
            sid = s.get("id", "?")
            title = (s.get("title") or s.get("url", ""))[:60]
            click.echo(f"  {sid:>6}  {title}")


def format_summary_detail(data: Any, json_mode: bool = False) -> None:
    """Format a single summary in detail."""
    if json_mode:
        format_json(data)
        return

    click.echo(f"ID:      {data.get('id')}")
    click.echo(f"Title:   {data.get('title', 'N/A')}")
    click.echo(f"URL:     {data.get('url', 'N/A')}")
    click.echo(f"Lang:    {data.get('language') or data.get('lang', 'N/A')}")
    click.echo(f"Read:    {'Yes' if data.get('isRead') or data.get('is_read') else 'No'}")
    click.echo(f"Fav:     {'Yes' if data.get('isFavorited') or data.get('is_favorited') else 'No'}")
    click.echo(f"Created: {data.get('createdAt') or data.get('created_at', 'N/A')}")

    tags = data.get("topicTags") or data.get("topic_tags") or data.get("tags") or []
    if tags:
        click.echo(f"Tags:    {', '.join(str(t) for t in tags)}")

    tldr = data.get("tldr") or data.get("summary250") or data.get("summary_250")
    if tldr:
        click.echo(f"\nTLDR: {tldr}")


def format_search_results(data: Any, json_mode: bool = False) -> None:
    """Format search results."""
    if json_mode:
        format_json(data)
        return

    results = data.get("results", [])
    total = data.get("totalCount") or data.get("total_count", len(results))
    took = data.get("tookMs") or data.get("took_ms", "?")

    click.echo(f"Found {total} results ({took}ms)")
    click.echo()

    for r in results:
        sid = r.get("id", "?")
        title = (r.get("title") or r.get("url", ""))[:60]
        domain = r.get("domain", "")
        click.echo(f"  {sid:>6}  {title}")
        if domain:
            click.echo(f"         {domain}")


def format_tags(data: Any, json_mode: bool = False) -> None:
    """Format tags list."""
    if json_mode:
        format_json(data)
        return

    tags = data if isinstance(data, list) else data.get("tags", [])
    if not tags:
        click.echo("No tags found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Tags")
        table.add_column("ID", width=6)
        table.add_column("Name")
        table.add_column("Color", width=8)
        table.add_column("Count", width=6)

        for t in tags:
            table.add_row(
                str(t.get("id", "")),
                t.get("name", ""),
                t.get("color", ""),
                str(t.get("summaryCount") or t.get("summary_count", 0)),
            )
        console.print(table)
    except ImportError:
        for t in tags:
            name = t.get("name", "?")
            count = t.get("summaryCount") or t.get("summary_count", 0)
            click.echo(f"  {name} ({count})")


def format_collections(data: Any, json_mode: bool = False) -> None:
    """Format collections list."""
    if json_mode:
        format_json(data)
        return

    collections = data if isinstance(data, list) else data.get("collections", [])
    if not collections:
        click.echo("No collections found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Collections")
        table.add_column("ID", width=6)
        table.add_column("Name")
        table.add_column("Type", width=8)
        table.add_column("Items", width=6)

        for c in collections:
            table.add_row(
                str(c.get("id", "")),
                c.get("name", ""),
                c.get("collectionType") or c.get("collection_type", "manual"),
                str(c.get("itemCount") or c.get("item_count", 0)),
            )
        console.print(table)
    except ImportError:
        for c in collections:
            name = c.get("name", "?")
            items = c.get("itemCount") or c.get("item_count", 0)
            click.echo(f"  {name} ({items} items)")


def echo_success(message: str) -> None:
    """Print a success message."""
    click.secho(message, fg="green")


def echo_error(message: str) -> None:
    """Print an error message."""
    click.secho(message, fg="red", err=True)
