"""Utilities for formatting Telegram messages consistently.

This module provides utilities for creating consistent, well-formatted
messages for Telegram, including progress bars and status messages.
"""


def create_progress_bar(current: int, total: int, width: int = 20) -> str:
    """Create a text-based progress bar.

    Args:
        current: Current progress value
        total: Total value for completion
        width: Width of the progress bar in characters (default: 20)

    Returns:
        A string representing the progress bar using block characters

    Example:
        >>> create_progress_bar(5, 10, 10)
        '█████░░░░░'
        >>> create_progress_bar(10, 10, 10)
        '██████████'
    """
    if total <= 0:
        return "░" * width

    filled = int(width * current / total)
    # Ensure we don't exceed width due to rounding
    filled = min(filled, width)
    empty = width - filled
    return "█" * filled + "░" * empty


def format_progress_message(
    current: int,
    total: int,
    *,
    prefix: str = "🔄 Processing",
    context: str = "links",
    show_bar: bool = True,
    bar_width: int = 20,
) -> str:
    """Format a consistent progress update message.

    Args:
        current: Current progress count
        total: Total items to process
        prefix: Prefix emoji/text for the message (default: "🔄 Processing")
        context: What is being processed (default: "links")
        show_bar: Whether to show a progress bar (default: True)
        bar_width: Width of the progress bar (default: 20)

    Returns:
        Formatted progress message string

    Example:
        >>> format_progress_message(5, 10)
        '🔄 Processing links: 5/10 (50%)\\n██████████░░░░░░░░░░'
        >>> format_progress_message(3, 10, context="files", show_bar=False)
        '🔄 Processing files: 3/10 (30%)'
    """
    percentage = int((current / total) * 100) if total > 0 else 0
    message = f"{prefix} {context}: {current}/{total} ({percentage}%)"

    if show_bar:
        progress_bar = create_progress_bar(current, total, bar_width)
        message += f"\n{progress_bar}"

    return message


def format_completion_message(
    total: int,
    successful: int,
    failed: int,
    *,
    context: str = "links",
    show_stats: bool = True,
    failure_rate_threshold: float = 20.0,
) -> str:
    """Format a completion message with success/failure statistics.

    Args:
        total: Total items processed
        successful: Number of successful items
        failed: Number of failed items
        context: What was being processed (default: "links")
        show_stats: Whether to show detailed statistics (default: True)
        failure_rate_threshold: Threshold percentage for changing message tone (default: 20.0)

    Returns:
        Formatted completion message string

    Example:
        >>> format_completion_message(10, 10, 0)
        '✅ Processing complete!\\n📊 Total: 10 links\\n✅ Successful: 10'
        >>> format_completion_message(10, 7, 3)
        '✅ Processing complete!\\n📊 Total: 10 links\\n✅ Successful: 7\\n❌ Failed: 3'
    """
    if failed == 0:
        # Perfect success
        return f"✅ Successfully processed all {successful} {context}!"

    if successful == 0:
        # Complete failure
        return f"❌ Failed to process any {context}. Please check if URLs are valid and accessible."

    # Partial success - analyze failure rate
    failure_rate = (failed / total) * 100 if total > 0 else 0

    if failure_rate <= failure_rate_threshold:
        # Low failure rate - optimistic message
        message = (
            f"✅ Processed {successful}/{total} {context} successfully! "
            f"({failed} failed - likely temporary issues)"
        )
    else:
        # High failure rate - more cautious message
        message = (
            f"⚠️ Processed {successful}/{total} {context} successfully. "
            f"{failed} failed. Some URLs may be inaccessible or invalid."
        )

    # Add detailed stats if requested
    if show_stats and total > 5:  # Only show for larger batches
        stats = f"\n📊 Total: {total} {context}\n✅ Successful: {successful}\n❌ Failed: {failed}"
        message += stats

    return message


def format_error_message(error: str, *, context: str = "processing") -> str:
    """Format a user-friendly error message.

    Args:
        error: The error message or description
        context: Context of what failed (default: "processing")

    Returns:
        Formatted error message string

    Example:
        >>> format_error_message("Network timeout", context="URL fetching")
        '❌ Error during URL fetching: Network timeout'
    """
    return f"❌ Error during {context}: {error}"
