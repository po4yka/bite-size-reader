"""Import and export commands."""

from __future__ import annotations

from pathlib import Path

import click
from ratatoskr_cli.auth import get_client
from ratatoskr_cli.output import echo_success, format_json


@click.command("export")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "csv", "html"]),
    default="json",
    help="Export format",
)
@click.option(
    "--output", "-o", "output_file", type=click.Path(), help="Output file (default: stdout)"
)
@click.pass_context
def export_cmd(ctx, fmt, output_file):
    """Export all data."""
    client = get_client(ctx.obj)
    data = client.export_data(fmt)

    if output_file:
        Path(output_file).write_bytes(data)
        echo_success(f"Exported to {output_file} ({len(data)} bytes)")
    else:
        # Write to stdout
        click.echo(data.decode("utf-8", errors="replace"))


@click.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--summarize", is_flag=True, help="Trigger summarization for imported items")
@click.pass_context
def import_cmd(ctx, file, summarize):
    """Import bookmarks from a file."""
    client = get_client(ctx.obj)
    result = client.import_file(Path(file), summarize=summarize)

    if ctx.obj["json"]:
        format_json(result)
    else:
        echo_success(f"Import started (job ID: {result.get('id')})")
        click.echo(f"  Format:  {result.get('sourceFormat') or result.get('source_format', '?')}")
        click.echo(f"  Items:   {result.get('totalItems') or result.get('total_items', 0)}")
        click.echo(f"  Status:  {result.get('status', '?')}")
