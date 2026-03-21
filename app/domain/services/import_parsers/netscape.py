"""Netscape HTML bookmark format parser.

Handles the standard browser bookmark export format (DT/A/DL tags).
"""

from __future__ import annotations

import html.parser
from datetime import UTC, datetime

from app.domain.services.import_parsers.base import ImportedBookmark


class _NetscapeHandler(html.parser.HTMLParser):
    """State-machine parser for Netscape bookmark HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.bookmarks: list[ImportedBookmark] = []
        self._folder_stack: list[str] = []
        self._current_attrs: dict[str, str] = {}
        self._in_a_tag: bool = False
        self._title_parts: list[str] = []
        self._in_h3: bool = False
        self._pending_folder: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower == "a":
            self._in_a_tag = True
            self._title_parts = []
            self._current_attrs = {k.upper(): v or "" for k, v in attrs}
        elif tag_lower == "h3":
            self._in_h3 = True
            self._title_parts = []
        elif tag_lower == "dl":
            if self._pending_folder is not None:
                self._folder_stack.append(self._pending_folder)
                self._pending_folder = None

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "a":
            self._flush_bookmark()
            self._in_a_tag = False
        elif tag_lower == "h3":
            self._pending_folder = "".join(self._title_parts).strip()
            self._in_h3 = False
        elif tag_lower == "dl":
            if self._folder_stack:
                self._folder_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_a_tag or self._in_h3:
            self._title_parts.append(data)

    def _flush_bookmark(self) -> None:
        href = self._current_attrs.get("HREF", "").strip()
        if not href:
            return

        title = "".join(self._title_parts).strip() or None
        tags_raw = self._current_attrs.get("TAGS", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        created_at: datetime | None = None
        add_date = self._current_attrs.get("ADD_DATE", "").strip()
        if add_date:
            try:
                created_at = datetime.fromtimestamp(int(add_date), tz=UTC)
            except (ValueError, OSError):
                pass

        collection = "/".join(self._folder_stack) if self._folder_stack else None

        self.bookmarks.append(
            ImportedBookmark(
                url=href,
                title=title,
                tags=tags,
                created_at=created_at,
                collection_name=collection,
            )
        )


class NetscapeHTMLParser:
    """Parse Netscape HTML bookmark export files."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        handler = _NetscapeHandler()
        try:
            handler.feed(text)
        except Exception:
            pass
        return handler.bookmarks
