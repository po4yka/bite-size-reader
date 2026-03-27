"""Repair broken HTML after text splitting/truncation.

Telegram's Bot API rejects messages with unclosed or orphaned HTML tags.
This module provides utilities to ensure each text chunk has balanced tags
after being split by character-boundary logic (chunk_text, validate_and_truncate).

Only handles the limited set of tags supported by Telegram Bot API:
b, i, u, s, code, pre, a, tg-spoiler, blockquote, tg-emoji
"""

from __future__ import annotations

import re

# Tags supported by Telegram Bot API (self-closing tags excluded).
# Order matters for closing: innermost first.
_TAG_RE = re.compile(r"<(/?)(\w[\w-]*)(?:\s[^>]*)?>")

_TELEGRAM_TAGS = frozenset(
    {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "blockquote", "tg-emoji"}
)


def repair_html_chunk(chunk: str) -> str:
    """Close unclosed tags and prepend re-opened tags from a broken split.

    Given a chunk that may start or end mid-tag-pair, this function:
    1. Closes any tags that were opened but never closed (appends closing tags).
    2. Prepends opening tags for any closing tags that appear without openers.

    This is intentionally simple -- it tracks a stack of open tag names by
    scanning all opening/closing tags in order.  It does NOT attempt to
    parse attributes for re-opened tags (Telegram only needs the tag name
    for continuation chunks).
    """
    if "<" not in chunk:
        return chunk

    # If the chunk was cut inside a tag (between < and >), trim the
    # partial tag to avoid sending malformed markup.
    chunk = _trim_partial_tag(chunk)

    # Build a stack of currently-open tags by replaying the chunk.
    open_stack: list[str] = []  # tag names, outermost first
    orphan_closers: list[str] = []  # closers with no matching opener

    for match in _TAG_RE.finditer(chunk):
        is_close = match.group(1) == "/"
        tag_name = match.group(2).lower()

        if tag_name not in _TELEGRAM_TAGS:
            continue

        if is_close:
            # Try to pop the matching opener from the stack (innermost first).
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i] == tag_name:
                    open_stack.pop(i)
                    break
            else:
                orphan_closers.append(tag_name)
        else:
            open_stack.append(tag_name)

    # Prepend openers for orphan closers (outermost first = order they appeared).
    prefix = "".join(f"<{tag}>" for tag in orphan_closers)

    # Append closers for still-open tags (innermost first = reverse stack order).
    suffix = "".join(f"</{tag}>" for tag in reversed(open_stack))

    return prefix + chunk + suffix


def _trim_partial_tag(text: str) -> str:
    """Remove a partial tag at the start or end of text.

    If text ends with an incomplete tag like ``<cod`` or ``<b class="x``,
    trim back to the last ``<`` that isn't closed by ``>``.
    Similarly, if text starts with a tag fragment like ``ode>`` or ``/b>``,
    trim forward past the first ``>``.
    """
    # Trailing partial: last '<' has no matching '>'
    last_lt = text.rfind("<")
    if last_lt != -1:
        after = text[last_lt:]
        if ">" not in after:
            text = text[:last_lt]

    # Leading partial: first '>' has no preceding '<' (in the leading segment)
    first_gt = text.find(">")
    if first_gt != -1:
        before = text[: first_gt + 1]
        if "<" not in before:
            text = text[first_gt + 1 :]

    return text
