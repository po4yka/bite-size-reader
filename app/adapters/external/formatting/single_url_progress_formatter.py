"""
Single-URL Progress Formatter.

Formats progress messages for single-URL processing (LLM analysis, YouTube downloads).
Similar to BatchProgressFormatter but tailored for single-URL workflows.
"""

import time


class SingleURLProgressFormatter:
    """Formats progress messages for single-URL operations."""

    @staticmethod
    def _html_escape(text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as human-readable string.

        Examples:
            12.5 -> "12s"
            75.0 -> "1m 15s"
            3665.0 -> "1h 1m"
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s" if secs > 0 else f"{mins}m"
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"

    @staticmethod
    def _get_spinner() -> str:
        """Get animated spinner character based on time.

        Returns a different frame every ~0.5s for smooth animation.
        """
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = int(time.time() * 2) % len(frames)
        return frames[idx]

    @classmethod
    def format_llm_progress(
        cls,
        content_length: int,
        model: str,
        elapsed_sec: float,
        phase: str = "analyzing",
    ) -> str:
        """Format LLM analysis progress message (HTML).

        Args:
            content_length: Number of characters in content
            model: LLM model name (e.g., "deepseek-v3.2")
            elapsed_sec: Elapsed time in seconds
            phase: Current phase ("analyzing", "retrying", "enriching")

        Returns:
            HTML-formatted progress message

        Example output:
            🧠 AI Analysis

            📝 Content: 12,450 chars
            🤖 Model: deepseek-v3.2
            ⏱️ Analyzing... (12s) ⠙

            Status: Processing with smart fallbacks
        """
        phase_labels = {
            "analyzing": "Analyzing...",
            "retrying": "Retrying with fallback...",
            "enriching": "Generating insights...",
        }
        phase_label = phase_labels.get(phase, "Processing...")

        spinner = cls._get_spinner()
        duration = cls._format_duration(elapsed_sec)
        content_formatted = f"{content_length:,}"

        return (
            f"🧠 <b>AI Analysis</b>\n\n"
            f"📝 Content: {content_formatted} chars\n"
            f"🤖 Model: {cls._html_escape(model)}\n"
            f"⏱️ {phase_label} ({duration}) {spinner}\n\n"
            f"<i>Status: Processing with smart fallbacks</i>"
        )

    @classmethod
    def format_llm_complete(
        cls,
        model: str,
        elapsed_sec: float,
        success: bool = True,
        error_msg: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """Format LLM completion message (HTML).

        Args:
            model: LLM model name
            elapsed_sec: Total elapsed time in seconds
            success: Whether analysis succeeded
            error_msg: Error message (if failed)
            correlation_id: Correlation ID for error tracking

        Returns:
            HTML-formatted completion message

        Success example:
            ✅ Analysis Complete (45s)

            📊 Summary generated
            🤖 Model: deepseek-v3.2

        Failure example:
            ❌ Analysis Failed (23s)

            Error: Timeout after 60s
            Error ID: abc123de
        """
        duration = cls._format_duration(elapsed_sec)

        if success:
            return (
                f"✅ <b>Analysis Complete</b> ({duration})\n\n"
                f"📊 Summary generated\n"
                f"🤖 Model: {cls._html_escape(model)}"
            )
        error_text = cls._html_escape(error_msg or "Unknown error")
        error_id_line = f"\nError ID: <code>{correlation_id}</code>" if correlation_id else ""
        return f"❌ <b>Analysis Failed</b> ({duration})\n\nError: {error_text}{error_id_line}"

    @classmethod
    def format_youtube_progress(
        cls,
        video_id: str,
        stage: int,
        stage_name: str,
        stage_elapsed_sec: float,
        completed_stages: list[tuple[str, float]],
        total_elapsed_sec: float,
    ) -> str:
        """Format YouTube download progress message (HTML).

        Args:
            video_id: YouTube video ID
            stage: Current stage number (1, 2, or 3)
            stage_name: Current stage description
            stage_elapsed_sec: Elapsed time for current stage
            completed_stages: List of (stage_name, duration) for completed stages
            total_elapsed_sec: Total elapsed time across all stages

        Returns:
            HTML-formatted progress message

        Example output:
            🎥 YouTube Video Processing

            Stage 1/3: ✅ Transcript extracted (8s)
            Stage 2/3: 📥 Downloading video... (45s) ⠸
            Video ID: abc123xyz
            Quality: 1080p

            Total: 53s
        """
        spinner = cls._get_spinner()
        stage_duration = cls._format_duration(stage_elapsed_sec)
        total_duration = cls._format_duration(total_elapsed_sec)

        # Build stage status lines
        stage_lines = []
        for idx, (name, duration) in enumerate(completed_stages, start=1):
            dur_str = cls._format_duration(duration)
            stage_lines.append(f"Stage {idx}/3: ✅ {name} ({dur_str})")

        # Current stage
        stage_lines.append(f"Stage {stage}/3: 📥 {stage_name} ({stage_duration}) {spinner}")

        stages_text = "\n".join(stage_lines)

        return (
            f"🎥 <b>YouTube Video Processing</b>\n\n"
            f"{stages_text}\n"
            f"Video ID: <code>{cls._html_escape(video_id)}</code>\n"
            f"Quality: 1080p\n\n"
            f"<b>Total:</b> {total_duration}"
        )

    @classmethod
    def format_youtube_complete(
        cls,
        title: str,
        size_mb: float,
        total_elapsed_sec: float,
        success: bool = True,
        error_msg: str | None = None,
        correlation_id: str | None = None,
        failed_stage: str | None = None,
    ) -> str:
        """Format YouTube completion message (HTML).

        Args:
            title: Video title
            size_mb: File size in megabytes
            total_elapsed_sec: Total elapsed time
            success: Whether processing succeeded
            error_msg: Error message (if failed)
            correlation_id: Correlation ID for error tracking
            failed_stage: Stage description where failure occurred

        Returns:
            HTML-formatted completion message

        Success example:
            ✅ Video Processing Complete (2m 48s)

            📹 Title: "How to Build AI Agents"
            💾 Size: 245.3 MB
            📝 Transcript ready

        Failure example:
            ❌ Video Processing Failed (1m 12s)

            Stage 2/3: Download failed
            Error: Connection timeout
            Error ID: xyz789ab
        """
        duration = cls._format_duration(total_elapsed_sec)

        if success:
            # Truncate title if too long
            display_title = title[:100] + "..." if len(title) > 100 else title
            return (
                f"✅ <b>Video Processing Complete</b> ({duration})\n\n"
                f"📹 Title: {cls._html_escape(display_title)}\n"
                f"💾 Size: {size_mb:.1f} MB\n"
                f"📝 Transcript ready"
            )
        error_text = cls._html_escape(error_msg or "Unknown error")
        error_id_line = f"\nError ID: <code>{correlation_id}</code>" if correlation_id else ""
        stage_line = f"{failed_stage}\n" if failed_stage else ""
        return (
            f"❌ <b>Video Processing Failed</b> ({duration})\n\n"
            f"{stage_line}"
            f"Error: {error_text}{error_id_line}"
        )
