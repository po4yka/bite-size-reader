"""Digest formatter -- builds Telegram messages with inline buttons."""

from __future__ import annotations

import logging
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096

CONTENT_TYPE_EMOJI: dict[str, str] = {
    "news": "\U0001f4f0",  # newspaper
    "tutorial": "\U0001f4d6",  # open book
    "opinion": "\U0001f4ac",  # speech balloon
    "other": "\U0001f4cc",  # pushpin
}


class DigestFormatter:
    """Formats analyzed posts into Telegram digest messages with inline buttons."""

    @staticmethod
    def format_digest(
        analyzed_posts: list[dict[str, Any]],
    ) -> list[tuple[str, list[list[dict[str, str]]]]]:
        """Format analyzed posts into Telegram-ready messages.

        Groups posts by channel (sorted by avg relevance desc), adds a table
        of contents, shows key_insights, and distributes inline buttons per
        message chunk.

        Args:
            analyzed_posts: List of post dicts with analysis fields.

        Returns:
            List of (message_text, inline_keyboard_rows) tuples.
        """
        if not analyzed_posts:
            return [("No new posts to digest.", [])]

        # Group by channel
        by_channel: dict[str, list[dict[str, Any]]] = {}
        for post in analyzed_posts:
            channel = post.get("_channel_username", "unknown")
            by_channel.setdefault(channel, []).append(post)

        # Sort each group by relevance desc
        for posts_list in by_channel.values():
            posts_list.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

        # Sort channels by average relevance desc, then alphabetically
        sorted_channels = sorted(
            by_channel.keys(),
            key=lambda ch: (
                -mean(p.get("relevance_score", 0) for p in by_channel[ch]),
                ch.lower(),
            ),
        )

        # --- Build header + table of contents ---
        total_posts = sum(len(v) for v in by_channel.values())
        total_channels = len(by_channel)
        parts: list[str] = [
            f"\U0001f4cb **Channel Digest** \u2014 "
            f"{total_posts} posts from {total_channels} channel{'s' if total_channels != 1 else ''}\n\n",
        ]
        for ch in sorted_channels:
            count = len(by_channel[ch])
            parts.append(f"  @{ch} \u2014 {count} post{'s' if count != 1 else ''}\n")
        parts.append("\n---\n")

        # --- Build post entries with per-post buttons ---
        # Track which post_num belongs to which line range so we can pair
        # buttons with the chunk that contains the post.
        post_entries: list[tuple[str, dict[str, str]]] = []
        post_num = 0
        for channel in sorted_channels:
            channel_header = f"\n\U0001f4e2 **@{channel}**\n"
            post_entries.append((channel_header, {}))

            for post in by_channel[channel]:
                post_num += 1
                content_type = post.get("content_type", "other")
                emoji = CONTENT_TYPE_EMOJI.get(content_type, "\U0001f4cc")

                real_topic = post.get("real_topic", "Untitled")
                tldr = post.get("tldr", "")

                lines = f"{post_num}. {emoji} **{real_topic}**\n    {tldr}\n"

                # Append key_insights as indented bullets
                key_insights: list[str] = post.get("key_insights") or []
                for insight in key_insights[:3]:
                    lines += f"    - {insight}\n"

                channel_id = post.get("_channel_id", 0)
                message_id = post.get("message_id", 0)
                button = {
                    "text": f"{post_num}. {real_topic[:30]}",
                    "callback_data": f"dg:{channel_id}:{message_id}",
                }
                post_entries.append((lines, button))

        # Combine header
        header_text = "".join(parts)

        # Split into chunks, distributing buttons
        return _split_with_buttons(header_text, post_entries)


def _split_with_buttons(
    header: str,
    entries: list[tuple[str, dict[str, str]]],
) -> list[tuple[str, list[list[dict[str, str]]]]]:
    """Build message chunks, attaching buttons for posts within each chunk."""
    result: list[tuple[str, list[list[dict[str, str]]]]] = []
    current_text = header
    current_buttons: list[list[dict[str, str]]] = []

    for entry_text, button in entries:
        candidate = current_text + entry_text
        if len(candidate) > MAX_MESSAGE_LENGTH and current_text.strip():
            result.append((current_text, current_buttons))
            current_text = entry_text
            current_buttons = []
        else:
            current_text = candidate
        if button:
            current_buttons.append([button])

    if current_text.strip():
        result.append((current_text, current_buttons))

    return result if result else [("No new posts to digest.", [])]
