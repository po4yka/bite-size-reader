"""Generic CSV bookmark import parser.

Expects headers: url (required), title, tags, notes, created_at.
Tags column may contain comma-separated values.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from app.domain.services.import_parsers.base import ImportedBookmark


class CsvBookmarkParser:
    """Parse CSV bookmark exports with a header row."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content

        bookmarks: list[ImportedBookmark] = []
        try:
            reader = csv.DictReader(io.StringIO(text))
        except Exception:
            return []

        for row in reader:
            try:
                url = (row.get("url") or "").strip()
                if not url:
                    continue

                tags: list[str] = []
                tags_raw = (row.get("tags") or "").strip()
                if tags_raw:
                    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

                notes = (row.get("notes") or "").strip() or None
                title = (row.get("title") or "").strip() or None

                created_at: datetime | None = None
                created_at_raw = (row.get("created_at") or "").strip()
                if created_at_raw:
                    try:
                        created_at = datetime.fromisoformat(created_at_raw)
                    except (ValueError, TypeError):
                        pass

                bookmarks.append(
                    ImportedBookmark(
                        url=url,
                        title=title,
                        tags=tags,
                        notes=notes,
                        created_at=created_at,
                    )
                )
            except Exception:
                continue

        return bookmarks
