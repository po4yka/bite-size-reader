"""Digest formatter -- builds Telegram messages with inline buttons."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096

CONTENT_TYPE_LABELS = {
    "news": "NEWS",
    "tutorial": "HOWTO",
    "opinion": "OPINION",
    "announcement": "ANN",
    "other": "POST",
}


class DigestFormatter:
    """Formats analyzed posts into Telegram digest messages with inline buttons."""

    @staticmethod
    def format_digest(
        analyzed_posts: list[dict[str, Any]],
    ) -> list[tuple[str, list[list[dict[str, str]]]]]:
        """Format analyzed posts into Telegram-ready messages.

        Groups posts by channel, sorts by relevance_score desc within groups.
        Splits into multiple messages if content exceeds Telegram limits.

        Args:
            analyzed_posts: List of post dicts with analysis fields.

        Returns:
            List of (message_text, inline_keyboard_rows) tuples.
            Each keyboard row is a list of button dicts with 'text' and 'callback_data'.
        """
        if not analyzed_posts:
            return [("No new posts to digest.", [])]

        # Group by channel
        by_channel: dict[str, list[dict[str, Any]]] = {}
        for post in analyzed_posts:
            channel = post.get("_channel_username", "unknown")
            by_channel.setdefault(channel, []).append(post)

        # Sort each group by relevance desc
        for _channel_key, posts_list in by_channel.items():
            posts_list.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

        # Build message parts
        parts: list[str] = []
        buttons: list[list[dict[str, str]]] = []

        parts.append("**Channel Digest**\n")

        for channel, posts in by_channel.items():
            parts.append(f"\n**@{channel}** ({len(posts)} posts)\n")

            for post in posts:
                content_type = post.get("content_type", "other")
                label = CONTENT_TYPE_LABELS.get(content_type, "POST")
                score = post.get("relevance_score", 0)
                score_bar = _score_indicator(score)

                real_topic = post.get("real_topic", "Untitled")
                tldr = post.get("tldr", "")

                line = f"  {score_bar} [{label}] **{real_topic}**\n  {tldr}\n"
                parts.append(line)

                # Inline button for full summary
                channel_id = post.get("_channel_id", 0)
                message_id = post.get("message_id", 0)
                buttons.append(
                    [
                        {
                            "text": f"Full: {real_topic[:30]}",
                            "callback_data": f"dg:{channel_id}:{message_id}",
                        }
                    ]
                )

        # Combine and split if needed
        full_text = "".join(parts)
        return _split_message(full_text, buttons)


def _score_indicator(score: float) -> str:
    """Convert 0.0-1.0 score to a text indicator."""
    if score >= 0.8:
        return "[!!!]"
    if score >= 0.6:
        return "[!! ]"
    if score >= 0.4:
        return "[!  ]"
    return "[   ]"


def _split_message(
    text: str,
    buttons: list[list[dict[str, str]]],
) -> list[tuple[str, list[list[dict[str, str]]]]]:
    """Split message into chunks respecting Telegram's 4096 char limit.

    Buttons are attached only to the last chunk.
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [(text, buttons)]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = current + line + "\n"
        if len(candidate) > MAX_MESSAGE_LENGTH:
            if current:
                chunks.append(current)
            current = line + "\n"
        else:
            current = candidate

    if current:
        chunks.append(current)

    if not chunks:
        return [(text[:MAX_MESSAGE_LENGTH], buttons)]

    # Attach buttons to last chunk only
    result: list[tuple[str, list[list[dict[str, str]]]]] = []
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            result.append((chunk, buttons))
        else:
            result.append((chunk, []))

    return result
