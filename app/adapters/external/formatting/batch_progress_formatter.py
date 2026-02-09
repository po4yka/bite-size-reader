"""Formatter for batch URL processing progress and completion messages.

Provides rich, informative messages showing per-URL status with numbered lines,
ETA estimates, and detailed completion reports with titles and error reasons.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.models.batch_processing import URLStatus

if TYPE_CHECKING:
    from app.models.batch_processing import URLBatchStatus, URLStatusEntry


# Telegram message limit with safety margin
MAX_MESSAGE_LENGTH = 3500


class BatchProgressFormatter:
    """Formats batch processing progress and completion messages.

    All output uses Telegram HTML parse mode. Callers must pass
    ``parse_mode="HTML"`` when sending/editing these messages.

    Provides multiple display formats:
    - Detailed: Numbered per-URL status lines with elapsed time
    - Compact: Summarized counts for long completion messages
    - Minimal: Simple counts for very long batches
    """

    # ------------------------------------------------------------------
    # HTML helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _html_escape(text: str) -> str:
        """Escape ``<``, ``>``, and ``&`` for safe Telegram HTML."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @classmethod
    def _make_link(cls, url: str, display_text: str) -> str:
        """Create an HTML ``<a>`` hyperlink safe for Telegram."""
        return f'<a href="{cls._html_escape(url)}">{cls._html_escape(display_text)}</a>'

    @classmethod
    def _get_spinner(cls, timestamp: float | None = None) -> str:
        """Get an 'animated' spinner based on current time or provided timestamp."""
        # Use provided timestamp or current time
        t = timestamp or time.time()
        # 4 frames, changes every 0.5s (2 frames per second)
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        return frames[int(t * 2) % len(frames)]

    @classmethod
    def format_progress_message(cls, batch: URLBatchStatus) -> str:
        """Format a progress update message with numbered per-URL status lines.

        Example output::

            Processing 4 links... ⠙

            [1/4] techcrunch.com -- Done (12s)
            [2/4] arxiv.org -- Analyzing... (5s)
            [Cache] medium.com -- Done
            [4/4] github.io -- Pending

            Progress: 2/4 (50%) | ETA: ~30s
            Updated 2s ago

        Args:
            batch: Current batch status

        Returns:
            Formatted progress message string
        """
        lines: list[str] = []
        total = batch.total
        spinner = cls._get_spinner()

        # Header
        lines.append(f"<b>Processing {total} links...</b> {spinner}")
        lines.append("")

        # Active work indicator (prominent top section)
        active = batch.processing
        if active:
            for entry in active[:2]:  # Show top 2 active tasks
                label = entry.title or entry.display_label or entry.domain
                if len(label) > 40:
                    label = label[:37] + "..."
                phase_emoji = "📥" if entry.status == URLStatus.EXTRACTING else "🧠"
                phase_name = "Extracting" if entry.status == URLStatus.EXTRACTING else "Analyzing"
                detail = ""
                if entry.status == URLStatus.ANALYZING:
                    parts = []
                    if entry.model:
                        m = entry.model.split("/")[-1]
                        parts.append(f"model: {m}")
                    if entry.content_length:
                        parts.append(f"size: {entry.content_length:,} chars")
                    if parts:
                        detail = f" ({', '.join(parts)})"

                lines.append(
                    f"{phase_emoji} <b>{phase_name}:</b> {cls._html_escape(label)}{detail} {spinner}"
                )
            lines.append("")

        # Per-URL status lines
        for index, entry in enumerate(batch.entries, 1):
            lines.append(cls._format_status_line(index, total, entry))

        lines.append("")

        # Footer: progress + ETA
        done = batch.done_count
        percentage = int((done / total) * 100) if total > 0 else 0
        footer_parts = [f"Progress: <b>{done}/{total}</b> ({percentage}%)"]

        eta_sec = batch.estimate_remaining_time_sec()
        if eta_sec is not None and eta_sec > 0:
            footer_parts.append(f"ETA: ~{cls._format_duration(eta_sec)}")

        lines.append(" | ".join(footer_parts))

        # Add "Last updated" info
        updated_ago = int(time.time() - batch.last_updated)
        if updated_ago > 0:
            lines.append(f"<i>Updated {updated_ago}s ago</i>")
        else:
            lines.append("<i>Just updated</i>")

        # Add hint for slow processing
        active = batch.processing
        if active:
            max_active_time = max((time.time() - (e.start_time or time.time())) for e in active)
            if max_active_time > 60:
                lines.append("")
                lines.append("<i>⌛ Heavily loaded source or complex content. Still working...</i>")

        message = "\n".join(lines)

        # Fallback to minimal if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            return cls._format_minimal_progress(batch)

        return message

    @classmethod
    def _format_status_line(cls, index: int, total: int, entry: URLStatusEntry) -> str:
        """Format a single numbered status line for progress display (HTML).

        The domain label is rendered as a clickable hyperlink to the original URL.
        Cached items use "[Cache]" prefix instead of numbers.

        Args:
            index: 1-based index of the entry
            total: Total number of entries in the batch
            entry: The URL status entry to format

        Returns:
            HTML-formatted status line, e.g.
            ``[2/5] <a href="...">arxiv.org</a>  Analyzing... (3s)``
        """
        is_cached = entry.status == URLStatus.CACHED
        prefix = "<code>[Cache]</code>" if is_cached else f"<code>[{index}/{total}]</code>"

        label = entry.display_label or entry.domain or "unknown"
        link = cls._make_link(entry.url, label)

        if entry.status == URLStatus.COMPLETE:
            elapsed = cls._format_elapsed(entry.processing_time_ms)
            return f"{prefix} {link}  ✅ Done{elapsed}"

        if entry.status == URLStatus.CACHED:
            return f"{prefix} {link}  ✅ Done (cached)"

        if entry.status == URLStatus.FAILED:
            error = cls._format_error_short(entry.error_type, entry.error_message)
            elapsed = cls._format_elapsed(entry.processing_time_ms)
            return f"{prefix} {link}  ❌ Failed: {cls._html_escape(error)}{elapsed}"

        if entry.status == URLStatus.EXTRACTING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {link}  📥 Extracting...{live} {cls._get_spinner()}"

        if entry.status == URLStatus.ANALYZING:
            live = cls._format_live_elapsed(entry.start_time)
            label = entry.title or label
            link = cls._make_link(entry.url, label)
            detail = ""
            if entry.model:
                m = entry.model.split("/")[-1]
                detail = f" [{m}]"
            return f"{prefix} {link}  🧠 Analyzing{detail}...{live} {cls._get_spinner()}"

        if entry.status == URLStatus.RETRYING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {link}  🔄 Retrying...{live} {cls._get_spinner()}"

        if entry.status == URLStatus.RETRY_WAITING:
            return f"{prefix} {link}  ⏳ Waiting to retry... {cls._get_spinner()}"

        if entry.status == URLStatus.PROCESSING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {link}  ⏳ Processing...{live} {cls._get_spinner()}"

        # PENDING (default)
        return f"{prefix} {link}  💤 Pending"

    @classmethod
    def _format_elapsed(cls, processing_time_ms: float) -> str:
        """Format completed processing time as a parenthesized suffix.

        Args:
            processing_time_ms: Processing time in milliseconds

        Returns:
            ``" (12s)"`` if time is positive, otherwise ``""``
        """
        if processing_time_ms > 0:
            seconds = processing_time_ms / 1000
            return f" ({cls._format_duration(seconds)})"
        return ""

    @classmethod
    def _format_live_elapsed(cls, start_time: float | None) -> str:
        """Format live elapsed time since processing started.

        Args:
            start_time: Unix timestamp when processing started, or None

        Returns:
            ``" (5s)"`` if elapsed >= 1 second, otherwise ``""``
        """
        if start_time is None:
            return ""
        elapsed = time.time() - start_time
        if elapsed >= 1:
            return f" ({cls._format_duration(elapsed)})"
        return ""

    @classmethod
    def format_completion_message(cls, batch: URLBatchStatus) -> str:
        """Format a completion message with a unified numbered list.

        Example output::

            Batch Complete -- 3/4 links

            1. "AI advances in 2026" -- techcrunch.com (12s)
            2. "Attention Is All You Need" -- arxiv.org (18s)
            3. "Rust vs Go" -- medium.com (15s)
            4. github.io -- Failed: Timeout (90s)

            Total: 1m 32s | Avg: 15s/link

        Args:
            batch: Completed batch status

        Returns:
            Formatted completion message string
        """
        lines: list[str] = []

        total = batch.total
        success = batch.success_count

        # Header
        total_time = batch.total_elapsed_time_sec()
        duration_str = cls._format_duration(total_time)
        lines.append(f"<b>Batch Complete</b>  {success}/{total} links ({duration_str})")
        lines.append("")

        # Unified numbered list (HTML)
        for index, entry in enumerate(batch.entries, 1):
            lines.append(cls._format_completion_line(index, entry))

        lines.append("")

        # Timing footer
        total_time = batch.total_elapsed_time_sec()
        avg_ms = batch.average_processing_time_ms()
        avg_str = cls._format_duration(avg_ms / 1000) if avg_ms > 0 else "N/A"
        lines.append(f"Total: {cls._format_duration(total_time)} | Avg: {avg_str}/link")

        message = "\n".join(lines)

        # Fallback to compact if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            return cls._format_compact_completion(batch)

        return message

    @classmethod
    def _format_completion_line(cls, index: int, entry: URLStatusEntry) -> str:
        """Format a single numbered line for the completion message (HTML).

        Successful entries use the article title as clickable link text.
        Failed entries use the domain/slug label as a clickable link.

        Args:
            index: 1-based index of the entry
            entry: The URL status entry to format

        Returns:
            HTML-formatted completion line, e.g.
            ``1. <a href="...">Article Title</a> (12s)``
        """
        label = entry.display_label or entry.domain or "unknown"
        elapsed = cls._format_elapsed(entry.processing_time_ms)

        if entry.status in {URLStatus.COMPLETE, URLStatus.CACHED}:
            title = entry.title or "Untitled"
            if len(title) > 50:
                title = title[:47] + "..."
            link = cls._make_link(entry.url, title)
            suffix = " (cached)" if entry.status == URLStatus.CACHED else elapsed
            return f"{index}. {link}{suffix}"

        if entry.status == URLStatus.FAILED:
            error = cls._format_error_short(entry.error_type, entry.error_message)
            link = cls._make_link(entry.url, label)
            return f"{index}. {link}  Failed: {cls._html_escape(error)}{elapsed}"

        # Shouldn't happen in a completed batch, but handle gracefully
        return f"{index}. {cls._html_escape(label)}  {cls._html_escape(entry.status.value)}"

    @classmethod
    def _format_minimal_progress(cls, batch: URLBatchStatus) -> str:
        """Format minimal progress message for very long batches."""
        done = batch.done_count
        total = batch.total
        percentage = int((done / total) * 100) if total > 0 else 0

        eta_sec = batch.estimate_remaining_time_sec()
        eta_part = f" | ETA: ~{cls._format_duration(eta_sec)}" if eta_sec else ""

        return f"Processing: {done}/{total} ({percentage}%){eta_part}"

    @classmethod
    def _format_compact_completion(cls, batch: URLBatchStatus) -> str:
        """Format compact completion message when detailed is too long (HTML)."""
        total = batch.total
        success = batch.success_count
        failed = batch.fail_count

        lines: list[str] = []

        # Header
        if failed == 0:
            lines.append(f"Batch Complete  All {success} links processed successfully!")
        elif success == 0:
            lines.append(f"Batch Failed  {failed} links failed")
        else:
            lines.append(f"Batch Complete  {success}/{total} links")
            lines.append(f"({failed} failed)")

        # Just show failed domains if any
        failed_entries = batch.failed
        if failed_entries:
            lines.append("")
            lines.append("Failed:")
            for entry in failed_entries[:3]:
                label = entry.display_label or entry.domain or entry.url[:20]
                error = cls._format_error_short(entry.error_type, entry.error_message)
                link = cls._make_link(entry.url, label)
                lines.append(f"  - {link}: {cls._html_escape(error)}")
            if len(failed_entries) > 3:
                lines.append(f"  ... and {len(failed_entries) - 3} more")

        # Timing
        total_time = batch.total_elapsed_time_sec()
        lines.append("")
        lines.append(f"Total: {cls._format_duration(total_time)}")

        return "\n".join(lines)

    @classmethod
    def _format_error_short(cls, error_type: str | None, error_message: str | None) -> str:
        """Format error for compact display."""
        if not error_type and not error_message:
            return "Unknown error"

        e_type = str(error_type).lower() if error_type else ""
        e_msg = str(error_message).lower() if error_message else ""

        if e_type == "timeout":
            if "after" in e_msg:
                return f"Timed out ({e_msg.split('after ')[-1]})"
            return "Timed out"

        if e_type == "domain_timeout":
            return "Skipped (slow site)"

        if e_type == "network":
            if "403" in e_msg:
                return "Access Denied (403)"
            if "404" in e_msg:
                return "Not Found (404)"
            return "Network error"

        if e_type == "validation":
            return "Invalid URL"

        if e_type in {"rate_limit", "429"}:
            return "Rate limited"

        if "refused" in e_msg:
            return "Connection refused"

        if "cloudflare" in e_msg:
            return "Blocked by Cloudflare"

        if error_message:
            # Truncate long error messages
            msg = str(error_message)
            if len(msg) > 30:
                return msg[:27] + "..."
            return msg

        return error_type or "Error"

    @classmethod
    def _format_duration(cls, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 1:
            return "<1s"
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            if secs > 0:
                return f"{minutes}m {secs}s"
            return f"{minutes}m"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

    @classmethod
    def get_current_processing_domain(cls, batch: URLBatchStatus) -> str | None:
        """Get the domain of the currently processing URL.

        Args:
            batch: Current batch status

        Returns:
            Domain string or None if nothing is processing
        """
        processing = batch.processing
        if processing:
            return processing[0].domain
        return None
