"""Karakeep JSON export parser.

Expected format: {"bookmarks": [{"url": "...", "title": "...", "tags": [...], "lists": [...], "note": "...", "createdAt": "ISO8601"}]}
"""

from __future__ import annotations

import json
from datetime import datetime

from app.domain.services.import_parsers.base import ImportedBookmark


class KarakeepParser:
    """Parse Karakeep JSON exports."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(data, dict):
            return []

        items = data.get("bookmarks")
        if not isinstance(items, list):
            return []

        bookmarks: list[ImportedBookmark] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url or not isinstance(url, str):
                continue

            tags: list[str] = []
            raw_tags = item.get("tags")
            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    if isinstance(tag, str) and tag:
                        tags.append(tag)

            collection_name: str | None = None
            lists = item.get("lists")
            if isinstance(lists, list) and lists:
                first = lists[0]
                if isinstance(first, str) and first:
                    collection_name = first

            notes: str | None = None
            note = item.get("note")
            if isinstance(note, str) and note.strip():
                notes = note.strip()

            created_at = _parse_iso(item.get("createdAt"))

            bookmarks.append(
                ImportedBookmark(
                    url=url,
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    tags=tags,
                    notes=notes,
                    created_at=created_at,
                    collection_name=collection_name,
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
