"""Formatter for batch URL processing progress and completion messages.

Provides rich, informative messages showing per-URL status, ETA estimates,
and detailed completion reports with titles and error reasons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.batch_processing import URLBatchStatus


# Telegram message limit with safety margin
MAX_MESSAGE_LENGTH = 3500


class BatchProgressFormatter:
    """Formats batch processing progress and completion messages.

    Provides multiple display formats:
    - Detailed: Full per-URL status with titles/errors
    - Compact: Grouped by status (Done/Now/Pending)
    - Minimal: Simple counts for very long messages
    """

    @classmethod
    def format_progress_message(cls, batch: URLBatchStatus) -> str:
        """Format a progress update message with per-URL status.

        Shows:
        - Completed URLs (by domain)
        - Currently processing URL
        - Pending count
        - Progress percentage
        - ETA based on average processing time

        Args:
            batch: Current batch status

        Returns:
            Formatted progress message string
        """
        lines: list[str] = []

        # Header
        lines.append(f"Processing {batch.total} links")
        lines.append("")

        # Completed URLs (show domains)
        completed = batch.completed
        if completed:
            domains = [e.domain or "unknown" for e in completed[:5]]
            domain_str = ", ".join(domains)
            if len(completed) > 5:
                domain_str += f" (+{len(completed) - 5} more)"
            lines.append(f"Done ({len(completed)}): {domain_str}")

        # Currently processing
        processing = batch.processing
        if processing:
            current = processing[0]
            lines.append(f"Now: {current.domain or current.url[:30]}")

        # Pending count
        pending_count = batch.pending_count
        if pending_count > 0:
            lines.append(f"Pending: {pending_count}")

        lines.append("")

        # Progress bar and percentage
        done = batch.done_count
        total = batch.total
        percentage = int((done / total) * 100) if total > 0 else 0
        lines.append(f"Progress: {done}/{total} ({percentage}%)")

        # ETA calculation
        eta_sec = batch.estimate_remaining_time_sec()
        avg_ms = batch.average_processing_time_ms()

        if eta_sec is not None and eta_sec > 0:
            eta_str = cls._format_duration(eta_sec)
            avg_str = cls._format_duration(avg_ms / 1000) if avg_ms > 0 else "?"
            lines.append(f"ETA: ~{eta_str} | Avg: {avg_str} per link")
        elif avg_ms > 0:
            avg_str = cls._format_duration(avg_ms / 1000)
            lines.append(f"Avg: {avg_str} per link")

        message = "\n".join(lines)

        # Fallback to minimal if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            return cls._format_minimal_progress(batch)

        return message

    @classmethod
    def format_completion_message(cls, batch: URLBatchStatus) -> str:
        """Format a completion message with detailed results.

        Shows:
        - Success/failure summary
        - List of successful URLs with titles
        - List of failed URLs with error reasons
        - Total time and average per link

        Args:
            batch: Completed batch status

        Returns:
            Formatted completion message string
        """
        lines: list[str] = []

        total = batch.total
        success = batch.success_count

        # Header with summary
        lines.append(f"Batch Complete - {success}/{total} links")
        lines.append("")

        # Successful URLs
        completed = batch.completed
        if completed:
            lines.append(f"Successful ({len(completed)}):")
            for i, entry in enumerate(completed[:10], 1):
                title = entry.title or "Untitled"
                domain = entry.domain or "unknown"
                # Truncate title if too long
                if len(title) > 50:
                    title = title[:47] + "..."
                lines.append(f'  {i}. "{title}" - {domain}')
            if len(completed) > 10:
                lines.append(f"  ... and {len(completed) - 10} more")
            lines.append("")

        # Failed URLs
        failed_entries = batch.failed
        if failed_entries:
            lines.append(f"Failed ({len(failed_entries)}):")
            for i, entry in enumerate(failed_entries[:5], 1):
                domain = entry.domain or entry.url[:30]
                error = cls._format_error_short(entry.error_type, entry.error_message)
                lines.append(f"  {i}. {domain} - {error}")
            if len(failed_entries) > 5:
                lines.append(f"  ... and {len(failed_entries) - 5} more")
            lines.append("")

        # Timing stats
        total_time = batch.total_elapsed_time_sec()
        avg_ms = batch.average_processing_time_ms()

        time_str = cls._format_duration(total_time)
        avg_str = cls._format_duration(avg_ms / 1000) if avg_ms > 0 else "N/A"
        lines.append(f"Total time: {time_str} | Avg: {avg_str} per link")

        message = "\n".join(lines)

        # Fallback to compact if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            return cls._format_compact_completion(batch)

        return message

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
            lines.append(f"Batch Complete - All {success} links processed successfully!")
        elif success == 0:
            lines.append(f"Batch Failed - {failed} links failed")
        else:
            lines.append(f"Batch Complete - {success}/{total} links")
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
        lines.append(f"Total time: {cls._format_duration(total_time)}")

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
