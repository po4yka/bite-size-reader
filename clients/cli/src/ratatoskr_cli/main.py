"""Ratatoskr CLI entry point."""

from __future__ import annotations

import click
from ratatoskr_cli import __version__
from ratatoskr_cli.output import echo_success, format_json


@click.group()
@click.version_option(version=__version__, prog_name="ratatoskr")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--server", envvar="RATATOSKR_SERVER_URL", help="Override server URL")
@click.pass_context
def cli(ctx: click.Context, json_output: bool, server: str | None) -> None:
    """Ratatoskr CLI -- save, search, and organize web content."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["server"] = server


# ---- Inline commands: config, login, whoami ----


@cli.command()
@click.option("--url", prompt="Server URL", help="Ratatoskr server URL")
def config(url: str) -> None:
    """Configure Ratatoskr server connection."""
    from ratatoskr_cli.config import load_config, save_config

    cfg = load_config()
    cfg.server_url = url.rstrip("/")
    save_config(cfg)
    echo_success(f"Server URL saved: {cfg.server_url}")


@cli.command()
@click.option("--server", prompt="Server URL", help="Ratatoskr server URL")
@click.option("--user-id", prompt="User ID", type=int, help="Telegram user ID")
@click.option("--client-id", prompt="Client ID", help="Client identifier")
@click.option("--secret", prompt="Secret", hide_input=True, help="Client secret")
def login(server: str, user_id: int, client_id: str, secret: str) -> None:
    """Authenticate with the Ratatoskr server."""
    from ratatoskr_cli.auth import login as auth_login

    cfg = auth_login(server.rstrip("/"), user_id, client_id, secret)
    echo_success(f"Logged in as user {cfg.user_id} on {cfg.server_url}")


@cli.command()
@click.pass_context
def whoami(ctx: click.Context) -> None:
    """Show current authenticated user."""
    from ratatoskr_cli.auth import get_client

    client = get_client(ctx.obj)
    result = client.whoami()
    if ctx.obj["json"]:
        format_json(result)
    else:
        click.echo(f"User ID:   {result.get('user_id', 'N/A')}")
        click.echo(f"Username:  {result.get('username', 'N/A')}")
        click.echo(f"Server:    {ctx.obj.get('server') or 'from config'}")


def _register_commands() -> None:
    """Register all command modules with the CLI group."""
    from ratatoskr_cli.commands.actions import delete, favorite, read_cmd
    from ratatoskr_cli.commands.admin import admin
    from ratatoskr_cli.commands.aggregation import aggregate, aggregation
    from ratatoskr_cli.commands.collections import collections
    from ratatoskr_cli.commands.get import get
    from ratatoskr_cli.commands.import_export import export_cmd, import_cmd
    from ratatoskr_cli.commands.list_cmd import list_cmd
    from ratatoskr_cli.commands.save import save
    from ratatoskr_cli.commands.search import search
    from ratatoskr_cli.commands.tags import tags

    cli.add_command(aggregate)
    cli.add_command(aggregation)
    cli.add_command(save)
    cli.add_command(list_cmd)
    cli.add_command(get)
    cli.add_command(search)
    cli.add_command(delete)
    cli.add_command(favorite)
    cli.add_command(read_cmd)
    cli.add_command(tags)
    cli.add_command(collections)
    cli.add_command(export_cmd)
    cli.add_command(import_cmd)
    cli.add_command(admin)


_register_commands()
