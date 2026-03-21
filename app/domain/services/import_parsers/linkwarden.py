"""Linkwarden JSON export parser.

Expected format: JSON array of objects with url, name, tags, collection, createdAt.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.domain.services.import_parsers.base import ImportedBookmark


class LinkwardenParser:
    """Parse Linkwarden JSON exports."""

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
            raw_tags = item.get("tags")
            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    name = tag.get("name") if isinstance(tag, dict) else None
                    if name and isinstance(name, str):
                        tags.append(name)

            collection_name: str | None = None
            collection = item.get("collection")
            if isinstance(collection, dict):
                cname = collection.get("name")
                if cname and isinstance(cname, str):
                    collection_name = cname

            created_at = _parse_iso(item.get("createdAt"))

            bookmarks.append(
                ImportedBookmark(
                    url=url,
                    title=item.get("name") if isinstance(item.get("name"), str) else None,
                    tags=tags,
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
