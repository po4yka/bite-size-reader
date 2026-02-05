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

    Provides multiple display formats:
    - Detailed: Numbered per-URL status lines with elapsed time
    - Compact: Summarized counts for long completion messages
    - Minimal: Simple counts for very long batches
    """

    @classmethod
    def format_progress_message(cls, batch: URLBatchStatus) -> str:
        """Format a progress update message with numbered per-URL status lines.

        Example output::

            Processing 4 links...

            [1/4] techcrunch.com -- Done (12s)
            [2/4] arxiv.org -- Analyzing... (5s)
            [3/4] medium.com -- Pending
            [4/4] github.io -- Pending

            Progress: 1/4 (25%) | ETA: ~45s

        Args:
            batch: Current batch status

        Returns:
            Formatted progress message string
        """
        lines: list[str] = []
        total = batch.total

        # Header
        lines.append(f"Processing {total} links...")
        lines.append("")

        # Per-URL status lines
        for index, entry in enumerate(batch.entries, 1):
            lines.append(cls._format_status_line(index, total, entry))

        lines.append("")

        # Footer: progress + ETA
        done = batch.done_count
        percentage = int((done / total) * 100) if total > 0 else 0
        footer_parts = [f"Progress: {done}/{total} ({percentage}%)"]

        eta_sec = batch.estimate_remaining_time_sec()
        if eta_sec is not None and eta_sec > 0:
            footer_parts.append(f"ETA: ~{cls._format_duration(eta_sec)}")

        lines.append(" | ".join(footer_parts))

        message = "\n".join(lines)

        # Fallback to minimal if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            return cls._format_minimal_progress(batch)

        return message

    @classmethod
    def _format_status_line(cls, index: int, total: int, entry: URLStatusEntry) -> str:
        """Format a single numbered status line for progress display.

        Args:
            index: 1-based index of the entry
            total: Total number of entries in the batch
            entry: The URL status entry to format

        Returns:
            Formatted status line, e.g. ``[2/5] arxiv.org -- Analyzing... (3s)``
        """
        prefix = f"[{index}/{total}]"
        domain = entry.domain or "unknown"

        if entry.status == URLStatus.COMPLETE:
            elapsed = cls._format_elapsed(entry.processing_time_ms)
            return f"{prefix} {domain} -- Done{elapsed}"

        if entry.status == URLStatus.FAILED:
            error = cls._format_error_short(entry.error_type, entry.error_message)
            elapsed = cls._format_elapsed(entry.processing_time_ms)
            return f"{prefix} {domain} -- Failed: {error}{elapsed}"

        if entry.status == URLStatus.EXTRACTING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {domain} -- Extracting...{live}"

        if entry.status == URLStatus.ANALYZING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {domain} -- Analyzing...{live}"

        if entry.status == URLStatus.PROCESSING:
            live = cls._format_live_elapsed(entry.start_time)
            return f"{prefix} {domain} -- Processing...{live}"

        # PENDING (default)
        return f"{prefix} {domain} -- Pending"

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
        lines.append(f"Batch Complete -- {success}/{total} links")
        lines.append("")

        # Unified numbered list
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
        """Format a single numbered line for the completion message.

        Args:
            index: 1-based index of the entry
            entry: The URL status entry to format

        Returns:
            Formatted completion line, e.g.
            ``1. "Article Title" -- techcrunch.com (12s)``
        """
        domain = entry.domain or "unknown"
        elapsed = cls._format_elapsed(entry.processing_time_ms)

        if entry.status == URLStatus.COMPLETE:
            title = entry.title or "Untitled"
            if len(title) > 50:
                title = title[:47] + "..."
            return f'{index}. "{title}" -- {domain}{elapsed}'

        if entry.status == URLStatus.FAILED:
            error = cls._format_error_short(entry.error_type, entry.error_message)
            return f"{index}. {domain} -- Failed: {error}{elapsed}"

        # Shouldn't happen in a completed batch, but handle gracefully
        return f"{index}. {domain} -- {entry.status.value}"

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
        """Format compact completion message when detailed is too long."""
        total = batch.total
        success = batch.success_count
        failed = batch.fail_count

        lines: list[str] = []

        # Header
        if failed == 0:
            lines.append(f"Batch Complete -- All {success} links processed successfully!")
        elif success == 0:
            lines.append(f"Batch Failed -- {failed} links failed")
        else:
            lines.append(f"Batch Complete -- {success}/{total} links")
            lines.append(f"({failed} failed)")

        # Just show failed domains if any
        failed_entries = batch.failed
        if failed_entries:
            lines.append("")
            lines.append("Failed:")
            for entry in failed_entries[:3]:
                domain = entry.domain or entry.url[:20]
                error = cls._format_error_short(entry.error_type, entry.error_message)
                lines.append(f"  - {domain}: {error}")
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
        if error_type == "timeout":
            # Extract timeout duration if present
            if error_message and "after" in error_message.lower():
                return error_message
            return "Timeout"
        if error_type == "network":
            return "Network error"
        if error_type == "validation":
            return "Invalid URL"
        if error_type in {"rate_limit", "429"}:
            return "Rate limited"
        if error_message:
            # Truncate long error messages
            msg = str(error_message)
            if len(msg) > 30:
                return msg[:27] + "..."
            return msg
        return error_type or "Unknown error"

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
