"""Database-related UI presentation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.adapters.external.formatting.data_formatter import DataFormatterImpl
    from app.adapters.external.formatting.response_sender import ResponseSenderImpl
    from app.services.topic_search import TopicArticle


class DatabasePresenterImpl:
    """Implementation of database-related UI presentation."""

    def __init__(
        self,
        response_sender: ResponseSenderImpl,
        data_formatter: DataFormatterImpl,
    ) -> None:
        """Initialize the database presenter.

        Args:
            response_sender: Response sender for sending messages.
            data_formatter: Data formatter for formatting values.
        """
        self._response_sender = response_sender
        self._data_formatter = data_formatter

    async def send_db_overview(self, message: Any, overview: dict[str, object]) -> None:
        """Send an overview of the database state."""
        lines = ["📚 Database Overview"]

        path_display = overview.get("path_display") or overview.get("path")
        if isinstance(path_display, str) and path_display:
            lines.append(f"Path: `{path_display}`")

        size_bytes = overview.get("db_size_bytes")
        if isinstance(size_bytes, int) and size_bytes >= 0:
            pretty_size = self._data_formatter.format_bytes(size_bytes)
            lines.append(f"Size: {pretty_size} ({size_bytes:,} bytes)")

        table_counts = overview.get("tables")
        if isinstance(table_counts, dict) and table_counts:
            lines.append("")
            lines.append("Tables:")
            for name in sorted(table_counts):
                lines.append(f"- {name}: {table_counts[name]}")
            truncated = overview.get("tables_truncated")
            if isinstance(truncated, int) and truncated > 0:
                lines.append(f"- ...and {truncated} more (not displayed)")

        total_requests = overview.get("total_requests")
        total_summaries = overview.get("total_summaries")
        totals: list[str] = []
        if isinstance(total_requests, int):
            totals.append(f"Requests: {total_requests}")
        if isinstance(total_summaries, int):
            totals.append(f"Summaries: {total_summaries}")
        if totals:
            lines.append("")
            lines.append("Totals: " + ", ".join(totals))

        statuses = overview.get("requests_by_status")
        if isinstance(statuses, dict) and statuses:
            lines.append("")
            lines.append("Requests by status:")
            for status in sorted(statuses):
                label = status or "unknown"
                lines.append(f"- {label}: {statuses[status]}")

        last_request = overview.get("last_request_at")
        last_summary = overview.get("last_summary_at")
        last_audit = overview.get("last_audit_at")
        timeline_parts: list[str] = []
        if isinstance(last_request, str) and last_request:
            timeline_parts.append(f"Last request: {last_request}")
        if isinstance(last_summary, str) and last_summary:
            timeline_parts.append(f"Last summary: {last_summary}")
        if isinstance(last_audit, str) and last_audit:
            timeline_parts.append(f"Last audit log: {last_audit}")
        if timeline_parts:
            lines.append("")
            lines.extend(timeline_parts)

        errors = overview.get("errors")
        if isinstance(errors, list) and errors:
            lines.append("")
            lines.append("Warnings:")
            for err in errors[:5]:
                lines.append(f"- {err}")

        await self._response_sender.safe_reply(message, "\n".join(lines))

    async def send_topic_search_results(
        self,
        message: Any,
        *,
        topic: str,
        articles: Sequence[TopicArticle],
        source: str = "online",
    ) -> None:
        """Send a formatted list of topic search results to the user."""

        topic_display = " ".join((topic or "").split())
        if not topic_display:
            topic_display = "your topic"
        if len(topic_display) > 120:
            topic_display = topic_display[:117].rstrip() + "..."

        source_key = (source or "").lower()
        if source_key == "library":
            header_icon = "🗄️"
            header_label = "Saved library results"
        elif source_key == "online":
            header_icon = "🌐"
            header_label = "Online search results"
        else:
            header_icon = "🔎"
            header_label = "Search results"

        lines: list[str] = [f"{header_icon} {header_label} for: {topic_display}"]

        for idx, article in enumerate(articles, start=1):
            title = article.title.strip() if article.title else article.url
            if len(title) > 180:
                title = title[:177].rstrip() + "..."

            lines.append(f"{idx}. {title}")
            lines.append(f"   🔗 {article.url}")

            details: list[str] = []
            if article.source:
                details.append(article.source)
            if article.published_at:
                details.append(article.published_at)
            if details:
                lines.append(f"   🗞️ {' · '.join(details)}")

            if article.snippet:
                lines.append(f"   📝 {article.snippet}")

            lines.append("")

        if lines and not lines[-1]:
            lines.pop()

        lines.append("")
        if source_key == "library":
            lines.append(
                "Tip: Send `/summarize <URL>` to refresh an article or `/read <request_id>` for saved summaries."
            )
        else:
            lines.append(
                "Tip: Send `/summarize <URL>` for a detailed summary of any article above."
            )

        await self._response_sender.safe_reply(message, "\n".join(lines))

    async def send_db_verification(self, message: Any, verification: dict[str, Any]) -> None:
        """Send database verification summary highlighting missing fields."""

        lines = ["🧪 Database Verification"]
        overview = verification.get("overview") if isinstance(verification, dict) else {}
        if isinstance(overview, dict):
            path_display = overview.get("path_display") or overview.get("path")
            if isinstance(path_display, str) and path_display:
                lines.append(f"Path: `{path_display}`")

            size_bytes = overview.get("db_size_bytes")
            if isinstance(size_bytes, int) and size_bytes >= 0:
                lines.append(
                    f"Size: {self._data_formatter.format_bytes(size_bytes)} ({size_bytes:,} bytes)"
                )

            table_counts = overview.get("tables")
            if isinstance(table_counts, dict) and table_counts:
                lines.append("")
                lines.append("Tables:")
                for name in sorted(table_counts):
                    lines.append(f"- {name}: {table_counts[name]}")

            statuses = overview.get("requests_by_status")
            if isinstance(statuses, dict) and statuses:
                lines.append("")
                lines.append("Request statuses:")
                for status in sorted(statuses):
                    lines.append(f"- {status or 'unknown'}: {statuses[status]}")

        posts = verification.get("posts") if isinstance(verification, dict) else {}
        if isinstance(posts, dict):
            required_fields = posts.get("required_fields")
            if isinstance(required_fields, list) and required_fields:
                preview = ", ".join(str(f) for f in required_fields[:8])
                if len(required_fields) > 8:
                    preview += ", …"
                lines.append("")
                lines.append(f"Fields checked: {preview}")

            checked = posts.get("checked")
            with_summary = posts.get("with_summary")
            if isinstance(checked, int) and checked > 0:
                lines.append("")
                summary_line = f"Posts checked: {checked}"
                if isinstance(with_summary, int):
                    summary_line += f" · With summary: {with_summary}"
                lines.append(summary_line)

            missing_summary = posts.get("missing_summary") or []
            if missing_summary:
                lines.append(f"⚠️ Missing summaries: {len(missing_summary)}")
                for entry in missing_summary[:5]:
                    rid = entry.get("request_id")
                    rtype = entry.get("type")
                    status = entry.get("status")
                    source = entry.get("source")
                    lines.append(f"  • #{rid} ({rtype} – {status}) {source}")
                remaining = len(missing_summary) - min(len(missing_summary), 5)
                if remaining > 0:
                    lines.append(f"  • … {remaining} more")

            missing_fields = posts.get("missing_fields") or []
            if missing_fields:
                lines.append("")
                lines.append(f"⚠️ Missing fields detected: {len(missing_fields)}")
                for entry in missing_fields[:5]:
                    rid = entry.get("request_id")
                    rtype = entry.get("type")
                    status = entry.get("status")
                    source = entry.get("source")
                    missing = entry.get("missing") or []
                    missing_preview = ", ".join(str(f) for f in missing[:6])
                    if len(missing) > 6:
                        missing_preview += ", …"
                    lines.append(f"  • #{rid} ({rtype} – {status}) {source} → {missing_preview}")
                remaining = len(missing_fields) - min(len(missing_fields), 5)
                if remaining > 0:
                    lines.append(f"  • … {remaining} more")

            links_info = posts.get("links") or {}
            if isinstance(links_info, dict):
                total_links = links_info.get("total_links")
                posts_with_links = links_info.get("posts_with_links")
                missing_links = links_info.get("missing_data") or []
                lines.append("")
                lines.append("Link coverage:")
                if isinstance(total_links, int):
                    lines.append(f"- Total captured links: {total_links}")
                if isinstance(posts_with_links, int):
                    lines.append(f"- Posts with link data: {posts_with_links}")
                if missing_links:
                    lines.append(f"- Missing link data: {len(missing_links)}")
                    for entry in missing_links[:5]:
                        rid = entry.get("request_id")
                        reason = entry.get("reason")
                        source = entry.get("source")
                        lines.append(f"  • #{rid} ({reason}) {source}")
                    remaining = len(missing_links) - min(len(missing_links), 5)
                    if remaining > 0:
                        lines.append(f"  • … {remaining} more")

            errors = posts.get("errors") or []
            if errors:
                lines.append("")
                lines.append("Warnings:")
                for err in errors[:5]:
                    lines.append(f"- {err}")
                if len(errors) > 5:
                    lines.append(f"- … {len(errors) - 5} more")

            reprocess_entries = posts.get("reprocess") or []
            if reprocess_entries:
                lines.append("")
                lines.append(f"🔄 Reprocess queue: {len(reprocess_entries)} posts")
                for entry in reprocess_entries[:5]:
                    rid = entry.get("request_id")
                    reason_list = entry.get("reasons") or []
                    reasons = ", ".join(reason_list[:4]) if reason_list else "unknown"
                    if reason_list and len(reason_list) > 4:
                        reasons += ", …"
                    source = (
                        entry.get("normalized_url") or entry.get("input_url") or entry.get("source")
                    )
                    lines.append(f"  • #{rid} → {source} ({reasons})")
                remaining = len(reprocess_entries) - min(len(reprocess_entries), 5)
                if remaining > 0:
                    lines.append(f"  • … {remaining} more")

            if missing_summary or missing_fields or errors:
                lines.append("")
                lines.append("Please reprocess the affected posts to regenerate missing data.")

        await self._response_sender.safe_reply(message, "\n".join(lines))

    async def send_db_reprocess_start(
        self,
        message: Any,
        *,
        url_targets: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
    ) -> None:
        """Notify the user that reprocessing of missing posts has started."""

        lines = ["🚀 Starting automated reprocessing"]

        if url_targets:
            lines.append(f"Processing {len(url_targets)} URL posts...")
            for entry in url_targets[:5]:
                rid = entry.get("request_id")
                url = entry.get("url")
                reasons = entry.get("reasons") or []
                reasons_text = ", ".join(reasons[:4]) if reasons else "missing data"
                if len(reasons) > 4:
                    reasons_text += ", …"
                lines.append(f"  • #{rid} {url} ({reasons_text})")
            if len(url_targets) > 5:
                lines.append(f"  • … {len(url_targets) - 5} more URLs")
        else:
            lines.append("No URL posts available for automatic reprocessing.")

        if skipped:
            lines.append("")
            lines.append(
                f"Skipped {len(skipped)} posts that require manual attention (e.g., forwards)."
            )

        await self._response_sender.safe_reply(message, "\n".join(lines))

    async def send_db_reprocess_complete(
        self,
        message: Any,
        *,
        url_targets: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
    ) -> None:
        """Summarize the outcome of the automated reprocessing."""

        total = len(url_targets)
        failed = len(failures)
        successful = total - failed

        status_icon = "✅" if failed == 0 else "⚠️"
        lines = [f"{status_icon} Reprocessing complete"]
        lines.append(f"Processed {successful}/{total} URL posts.")

        if failures:
            lines.append("Failures:")
            for entry in failures[:5]:
                rid = entry.get("request_id")
                url = entry.get("url")
                error = entry.get("error") or "unknown error"
                lines.append(f"  • #{rid} {url}: {error}")
            if failed > 5:
                lines.append(f"  • … {failed - 5} more failures")

        if skipped:
            lines.append("")
            lines.append(f"Skipped {len(skipped)} posts that could not be retried automatically.")

        await self._response_sender.safe_reply(message, "\n".join(lines))
