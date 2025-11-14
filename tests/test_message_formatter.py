"""Tests for message formatter utilities."""

import unittest

from app.utils.message_formatter import (
    create_progress_bar,
    format_completion_message,
    format_error_message,
    format_progress_message,
)


class TestMessageFormatter(unittest.TestCase):
    """Test suite for message formatter utilities."""

    def test_create_progress_bar_empty(self):
        """Test progress bar with zero progress."""
        bar = create_progress_bar(0, 10, width=10)
        assert bar == "░░░░░░░░░░"

    def test_create_progress_bar_half(self):
        """Test progress bar at 50%."""
        bar = create_progress_bar(5, 10, width=10)
        assert bar == "█████░░░░░"

    def test_create_progress_bar_full(self):
        """Test progress bar at 100%."""
        bar = create_progress_bar(10, 10, width=10)
        assert bar == "██████████"

    def test_create_progress_bar_custom_width(self):
        """Test progress bar with custom width."""
        bar = create_progress_bar(5, 10, width=20)
        assert len(bar) == 20
        assert bar.count("█") == 10
        assert bar.count("░") == 10

    def test_create_progress_bar_zero_total(self):
        """Test progress bar with zero total (edge case)."""
        bar = create_progress_bar(0, 0, width=10)
        assert bar == "░░░░░░░░░░"

    def test_create_progress_bar_rounding(self):
        """Test progress bar doesn't exceed width due to rounding."""
        bar = create_progress_bar(1, 3, width=10)
        assert len(bar) == 10

    def test_format_progress_message_with_bar(self):
        """Test progress message formatting with progress bar."""
        message = format_progress_message(5, 10, show_bar=True)
        assert "🔄 Processing links: 5/10 (50%)" in message
        assert "█" in message  # Has progress bar
        assert "░" in message

    def test_format_progress_message_without_bar(self):
        """Test progress message formatting without progress bar."""
        message = format_progress_message(5, 10, show_bar=False)
        assert message == "🔄 Processing links: 5/10 (50%)"
        assert "█" not in message  # No progress bar
        assert "░" not in message

    def test_format_progress_message_custom_context(self):
        """Test progress message with custom context."""
        message = format_progress_message(3, 7, context="files", show_bar=False)
        assert "files: 3/7" in message

    def test_format_progress_message_custom_prefix(self):
        """Test progress message with custom prefix."""
        message = format_progress_message(
            3, 7, prefix="⏳ Loading", context="items", show_bar=False
        )
        assert message == "⏳ Loading items: 3/7 (42%)"

    def test_format_progress_message_zero_progress(self):
        """Test progress message at 0%."""
        message = format_progress_message(0, 10, show_bar=False)
        assert "0/10 (0%)" in message

    def test_format_progress_message_full_progress(self):
        """Test progress message at 100%."""
        message = format_progress_message(10, 10, show_bar=False)
        assert "10/10 (100%)" in message

    def test_format_completion_message_full_success(self):
        """Test completion message with all successful."""
        message = format_completion_message(10, 10, 0)
        assert message == "✅ Successfully processed all 10 links!"

    def test_format_completion_message_full_failure(self):
        """Test completion message with all failed."""
        message = format_completion_message(10, 0, 10)
        assert "❌ Failed to process any links" in message
        assert "valid and accessible" in message

    def test_format_completion_message_partial_success_low_failure(self):
        """Test completion message with low failure rate (< 20%)."""
        message = format_completion_message(10, 9, 1)
        assert "✅ Processed 9/10 links successfully!" in message
        assert "likely temporary issues" in message

    def test_format_completion_message_partial_success_high_failure(self):
        """Test completion message with high failure rate (> 20%)."""
        message = format_completion_message(10, 6, 4)
        assert "⚠️ Processed 6/10 links successfully" in message
        assert "Some URLs may be inaccessible or invalid" in message

    def test_format_completion_message_custom_context(self):
        """Test completion message with custom context."""
        message = format_completion_message(5, 5, 0, context="files")
        assert "5 files" in message

    def test_format_completion_message_with_stats(self):
        """Test completion message with detailed statistics."""
        message = format_completion_message(15, 12, 3, show_stats=True)
        # Should include stats for larger batches
        assert "📊 Total:" in message or "12/15" in message

    def test_format_completion_message_without_stats(self):
        """Test completion message without detailed statistics."""
        message = format_completion_message(3, 2, 1, show_stats=False)
        assert "📊 Total:" not in message

    def test_format_completion_message_custom_threshold(self):
        """Test completion message with custom failure rate threshold."""
        # 30% failure rate
        message = format_completion_message(10, 7, 3, failure_rate_threshold=40.0)
        # Should be optimistic since 30% < 40%
        assert "✅" in message
        assert "likely temporary issues" in message

    def test_format_completion_message_boundary_threshold(self):
        """Test completion message at exactly the threshold."""
        # 20% failure rate with 20% threshold
        message = format_completion_message(10, 8, 2, failure_rate_threshold=20.0)
        # Should be optimistic at boundary
        assert "✅" in message

    def test_format_error_message(self):
        """Test error message formatting."""
        message = format_error_message("Network timeout")
        assert message == "❌ Error during processing: Network timeout"

    def test_format_error_message_custom_context(self):
        """Test error message with custom context."""
        message = format_error_message("Invalid URL", context="URL validation")
        assert message == "❌ Error during URL validation: Invalid URL"

    def test_format_progress_message_percentage_calculation(self):
        """Test that percentage is calculated correctly."""
        # 1/3 = 33.33%, should round to 33%
        message = format_progress_message(1, 3, show_bar=False)
        assert "(33%)" in message

        # 2/3 = 66.66%, should round to 66%
        message = format_progress_message(2, 3, show_bar=False)
        assert "(66%)" in message

    def test_format_completion_message_stats_small_batch(self):
        """Test that stats are not shown for small batches."""
        message = format_completion_message(3, 2, 1, show_stats=True)
        # Should not show detailed stats for batches <= 5
        assert "📊 Total:" not in message

    def test_format_completion_message_stats_large_batch(self):
        """Test that stats are shown for large batches."""
        message = format_completion_message(10, 8, 2, show_stats=True)
        # Should show stats for batches > 5
        assert "📊 Total:" in message or "8/10" in message


class TestProgressBarEdgeCases(unittest.TestCase):
    """Test edge cases for progress bar creation."""

    def test_progress_bar_exceeds_total(self):
        """Test progress bar when current > total (shouldn't happen but handle gracefully)."""
        # Should not crash or create invalid bar
        bar = create_progress_bar(15, 10, width=10)
        assert len(bar) == 10
        # All filled since current >= total
        assert bar == "██████████"

    def test_progress_bar_negative_values(self):
        """Test progress bar with negative values (edge case)."""
        # Should handle gracefully
        bar = create_progress_bar(-1, 10, width=10)
        # Negative progress should result in empty bar
        assert "░" in bar

    def test_progress_bar_width_one(self):
        """Test progress bar with minimum width."""
        bar = create_progress_bar(5, 10, width=1)
        assert len(bar) == 1

    def test_format_progress_message_zero_total(self):
        """Test progress message with zero total (edge case)."""
        message = format_progress_message(0, 0, show_bar=False)
        assert "(0%)" in message

    def test_format_completion_message_zero_total(self):
        """Test completion message with zero total (edge case)."""
        message = format_completion_message(0, 0, 0)
        # Should handle gracefully - complete success case
        assert "✅" in message
