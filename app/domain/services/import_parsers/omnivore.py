"""Omnivore JSON export parser.

Expected format: JSON array of objects with url, title, labels, highlights, savedAt.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.domain.services.import_parsers.base import ImportedBookmark


class OmnivoreParser:
    """Parse Omnivore JSON exports."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(data, list):
            return []

        bookmarks: list[ImportedBookmark] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url or not isinstance(url, str):
                continue

            tags: list[str] = []
            labels = item.get("labels")
            if isinstance(labels, list):
                for label in labels:
                    name = label.get("name") if isinstance(label, dict) else None
                    if name and isinstance(name, str):
                        tags.append(name)

            created_at = _parse_iso(item.get("savedAt"))

            highlights: list[dict] | None = None
            raw_highlights = item.get("highlights")
            if isinstance(raw_highlights, list) and raw_highlights:
                highlights = [h for h in raw_highlights if isinstance(h, dict)]

            bookmarks.append(
                ImportedBookmark(
                    url=url,
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    tags=tags,
                    created_at=created_at,
                    highlights=highlights or None,
                )
            )
        return bookmarks


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
