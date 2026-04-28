"""Ratatoskr CLI output formatters."""

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


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            value = data[key]
            if value is not None and value != "":
                return value
    return default


def _as_list(data: Any, *keys: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _format_count(value: Any) -> str:
    return str(value) if value is not None else "?"


def _format_failure(failure: Any) -> str | None:
    if not isinstance(failure, dict):
        return None
    code = _pick(failure, "code", "failure_code")
    message = _pick(failure, "message", "failure_message")
    if code and message:
        return f"{code}: {message}"
    if code:
        return str(code)
    if message:
        return str(message)
    return None


def format_aggregation_detail(data: Any, json_mode: bool = False) -> None:
    """Format a single aggregation session with summary and item details."""
    if json_mode:
        format_json(data)
        return

    session = data.get("session") if isinstance(data, dict) else data
    if not isinstance(session, dict):
        session = {}

    aggregation: dict[str, Any] = {}
    if isinstance(data, dict):
        aggregation = data.get("aggregation") or data.get("aggregation_output_json") or {}
    if not isinstance(aggregation, dict):
        aggregation = {}

    items = _as_list(data, "items")

    session_id = _pick(session, "sessionId", "id", "session_id")
    status = _pick(session, "status", default="N/A")
    correlation_id = _pick(session, "correlationId", "correlation_id")
    source_type = _pick(session, "sourceType", "source_type")
    total_items = _pick(session, "totalItems", "total_items", default=len(items) or None)
    successful_count = _pick(session, "successfulCount", "successful_count")
    failed_count = _pick(session, "failedCount", "failed_count")
    duplicate_count = _pick(session, "duplicateCount", "duplicate_count")
    created_at = _pick(session, "createdAt", "created_at")
    queued_at = _pick(session, "queuedAt", "queued_at")
    started_at = _pick(session, "startedAt", "started_at")
    completed_at = _pick(session, "completedAt", "completed_at")
    last_progress_at = _pick(session, "lastProgressAt", "last_progress_at")
    updated_at = _pick(session, "updatedAt", "updated_at")
    processing_time_ms = _pick(session, "processingTimeMs", "processing_time_ms")
    failure_text = _format_failure(session.get("failure") if isinstance(session, dict) else None)
    failure_code = _pick(session, "failureCode", "failure_code")
    failure_message = _pick(session, "failureMessage", "failure_message")

    click.echo("Aggregation Session")
    click.echo(f"ID:       {session_id if session_id is not None else 'N/A'}")
    click.echo(f"Status:   {status}")
    if correlation_id:
        click.echo(f"Correlation: {correlation_id}")
    if source_type:
        click.echo(f"Source Type: {source_type}")
    click.echo(
        "Counts:   "
        f"{_format_count(total_items)} total, "
        f"{_format_count(successful_count)} successful, "
        f"{_format_count(failed_count)} failed, "
        f"{_format_count(duplicate_count)} duplicates"
    )
    if queued_at:
        click.echo(f"Queued:   {queued_at}")
    if started_at:
        click.echo(f"Started:  {started_at}")
    if completed_at:
        click.echo(f"Completed:{completed_at}")
    if last_progress_at:
        click.echo(f"Progress: {last_progress_at}")
    if processing_time_ms is not None:
        click.echo(f"Latency:  {processing_time_ms}ms")
    if created_at:
        click.echo(f"Created:  {created_at}")
    if updated_at:
        click.echo(f"Updated:  {updated_at}")
    if failure_text or failure_code or failure_message:
        failure_line = failure_text or "Unknown failure"
        click.echo(f"Failure:  {failure_line}")

    summary = _pick(aggregation, "tldr", "summary_250", "summary250")
    long_summary = _pick(aggregation, "summary_1000", "summary1000")
    overview = _pick(aggregation, "overview")
    key_ideas = _as_list(aggregation, "key_ideas", "keyIdeas")
    progress = session.get("progress") if isinstance(session, dict) else None

    if summary or long_summary or overview or key_ideas:
        click.echo("\nAggregation Output")

    if overview:
        click.echo(f"Overview: {overview}")
    if summary:
        click.echo(f"TLDR: {summary}")
    if long_summary and long_summary != summary:
        click.echo(f"\nSummary: {long_summary}")
    if key_ideas:
        click.echo("\nKey Ideas:")
        for idea in key_ideas:
            click.echo(f"  - {idea}")
    if isinstance(progress, dict):
        completion_percent = _pick(progress, "completionPercent", "completion_percent")
        processed_items = _pick(progress, "processedItems", "processed_items")
        if completion_percent is not None or processed_items is not None:
            click.echo(
                "\nProgress: "
                f"{_format_count(processed_items)} processed, "
                f"{_format_count(completion_percent)}%"
            )

    if items:
        click.echo("\nItems:")
        for item in items:
            if not isinstance(item, dict):
                click.echo(f"  - {item}")
                continue
            position = _pick(item, "position")
            item_status = _pick(item, "status", default="unknown")
            source_kind = _pick(item, "sourceKind", "source_kind")
            source_value = _pick(
                item,
                "url",
                "originalValue",
                "original_value",
                "normalizedValue",
                "normalized_value",
                "sourceItemId",
                "source_item_id",
            )
            line = f"  - {item_status}"
            if position is not None:
                line = f"  - [{position}] {item_status}"
            if source_kind:
                line += f" ({source_kind})"
            if source_value:
                line += f": {source_value}"
            item_failure = _format_failure(item.get("failure"))
            if item_failure:
                line += f" [{item_failure}]"
            click.echo(line)


def format_aggregation_list(data: Any, json_mode: bool = False) -> None:
    """Format a list of aggregation sessions."""
    if json_mode:
        format_json(data)
        return

    sessions = _as_list(data, "sessions", "aggregations", "items")
    if not sessions:
        click.echo("No aggregation sessions found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Aggregation Sessions")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Status", width=12)
        table.add_column("Items", width=8)
        table.add_column("Succ", width=6)
        table.add_column("Fail", width=6)
        table.add_column("Dup", width=6)
        table.add_column("Created", width=20)

        for session in sessions:
            if not isinstance(session, dict):
                table.add_row(str(session), "", "", "", "", "", "")
                continue
            table.add_row(
                str(_pick(session, "sessionId", "id", "session_id", default="")),
                str(_pick(session, "status", default="")),
                _format_count(_pick(session, "totalItems", "total_items")),
                _format_count(_pick(session, "successfulCount", "successful_count")),
                _format_count(_pick(session, "failedCount", "failed_count")),
                _format_count(_pick(session, "duplicateCount", "duplicate_count")),
                str(_pick(session, "createdAt", "created_at", default=""))[:20],
            )

        console.print(table)
    except ImportError:
        for session in sessions:
            if not isinstance(session, dict):
                click.echo(f"  {session}")
                continue
            sid = _pick(session, "sessionId", "id", "session_id", default="?")
            status = _pick(session, "status", default="?")
            total = _format_count(_pick(session, "totalItems", "total_items"))
            success = _format_count(_pick(session, "successfulCount", "successful_count"))
            failed = _format_count(_pick(session, "failedCount", "failed_count"))
            dup = _format_count(_pick(session, "duplicateCount", "duplicate_count"))
            created = _pick(session, "createdAt", "created_at", default="?")
            click.echo(
                f"  {sid:>6}  {status:<12} items={total} succ={success} fail={failed} dup={dup}  {created}"
            )


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
