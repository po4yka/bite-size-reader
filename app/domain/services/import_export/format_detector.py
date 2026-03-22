"""Detect import file format from filename and content.

Pure function -- no DB or network access.
"""

from __future__ import annotations

import json


class FormatDetector:
    """Detect import file format from filename and content."""

    @staticmethod
    def detect(filename: str, content: bytes) -> str:
        """Return format string: netscape_html, pocket, omnivore, linkwarden, csv, opml, unknown."""
        ext = _extension(filename)

        if ext == ".csv":
            return "csv"

        if ext == ".opml":
            return "opml"

        if ext in {".html", ".htm"}:
            return _detect_html(content)

        if ext == ".json":
            return _detect_json(content)

        if ext == ".xml":
            return _detect_xml(content)

        return "unknown"


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()


def _detect_html(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return "unknown"

    upper = text[:2048].upper()

    if "<!DOCTYPE NETSCAPE-BOOKMARK" not in upper:
        return "unknown"

    # Pocket exports typically have a specific structure:
    # <h1>Bookmarks</h1> near the top, and Pocket-specific attributes
    head = text[:4096]
    if "<h1>Bookmarks</h1>" in head or "getpocket.com" in head.lower():
        return "pocket"

    return "netscape_html"


def _detect_json(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError, Exception):
        return "unknown"

    if isinstance(data, dict):
        return "unknown"

    if isinstance(data, list) and len(data) > 0:
        first = data[0] if isinstance(data[0], dict) else {}

        if "labels" in first:
            return "omnivore"

        if "collection" in first:
            tags = first.get("tags")
            if isinstance(tags, list) and len(tags) > 0:
                tag = tags[0]
                if isinstance(tag, dict) and "name" in tag:
                    return "linkwarden"

        return "unknown"

    return "unknown"


def _detect_xml(content: bytes) -> str:
    try:
        text = content[:2048].decode("utf-8", errors="replace").lower()
    except Exception:
        return "unknown"

    if "<opml" in text:
        return "opml"

    return "unknown"
