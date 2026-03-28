"""Admin commands (owner-only)."""

from __future__ import annotations

import click
from bsr_cli.auth import get_client
from bsr_cli.output import format_json


@click.group()
@click.pass_context
def admin(ctx):
    """Admin operations (owner-only)."""


@admin.command("users")
@click.pass_context
def admin_users(ctx):
    """List all users with stats."""
    client = get_client(ctx.obj)
    result = client.admin_users()

    if ctx.obj["json"]:
        format_json(result)
        return

    users = result.get("users", []) if isinstance(result, dict) else result
    click.echo(f"Total users: {len(users)}")
    for u in users:
        uid = u.get("userId") or u.get("user_id", "?")
        username = u.get("username", "?")
        summaries = u.get("summaryCount") or u.get("summary_count", 0)
        owner = " (owner)" if u.get("isOwner") or u.get("is_owner") else ""
        click.echo(f"  {uid}  @{username}  {summaries} summaries{owner}")


@admin.command("health")
@click.pass_context
def admin_health(ctx):
    """Show content health report."""
    client = get_client(ctx.obj)
    result = client.admin_health()

    if ctx.obj["json"]:
        format_json(result)
        return

    click.echo(
        f"Total summaries: {result.get('totalSummaries') or result.get('total_summaries', '?')}"
    )
    click.echo(
        f"Total requests:  {result.get('totalRequests') or result.get('total_requests', '?')}"
    )
    click.echo(
        f"Failed:          {result.get('failedRequests') or result.get('failed_requests', 0)}"
    )

    breakdown = result.get("failedByErrorType") or result.get("failed_by_error_type", {})
    if breakdown:
        click.echo("\nError breakdown:")
        for err_type, count in breakdown.items():
            click.echo(f"  {err_type}: {count}")


@admin.command("jobs")
@click.pass_context
def admin_jobs(ctx):
    """Show background job status."""
    client = get_client(ctx.obj)
    result = client.admin_jobs()

    if ctx.obj["json"]:
        format_json(result)
        return

    pipeline = result.get("pipeline", {})
    click.echo("Pipeline:")
    click.echo(f"  Pending:        {pipeline.get('pending', pipeline.get('pendingRequests', 0))}")
    click.echo(
        f"  Processing:     {pipeline.get('processing', pipeline.get('processingRequests', 0))}"
    )
    click.echo(
        f"  Completed today: {pipeline.get('completedToday') or pipeline.get('completed_today', 0)}"
    )
    click.echo(
        f"  Failed today:    {pipeline.get('failedToday') or pipeline.get('failed_today', 0)}"
    )

    imports = result.get("imports", {})
    if imports:
        click.echo("\nImports:")
        click.echo(f"  Active:          {imports.get('active', imports.get('activeJobs', 0))}")
        click.echo(
            f"  Completed today: {imports.get('completedToday') or imports.get('completed_today', 0)}"
        )
