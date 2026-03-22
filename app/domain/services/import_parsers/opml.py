"""OPML feed list parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

import defusedxml.ElementTree as DefusedET

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

from app.domain.services.import_parsers.base import ImportedBookmark


class OPMLParser:
    """Parse OPML files into a list of feed bookmarks."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        try:
            root = DefusedET.fromstring(content)
        except DefusedET.ParseError:
            return []

        bookmarks: list[ImportedBookmark] = []
        body = root.find("body")
        if body is None:
            return bookmarks

        self._parse_outlines(body, bookmarks, category=None)
        return bookmarks

    def _parse_outlines(
        self, element: Element, bookmarks: list[ImportedBookmark], category: str | None
    ) -> None:
        for outline in element.findall("outline"):
            xml_url = outline.get("xmlUrl")
            if xml_url:
                # This is a feed entry
                bookmarks.append(
                    ImportedBookmark(
                        url=xml_url,
                        title=outline.get("text") or outline.get("title"),
                        collection_name=category,
                        extra={
                            "feed_type": "rss",
                            "html_url": outline.get("htmlUrl"),
                            "outline_type": outline.get("type", "rss"),
                        },
                    )
                )
            else:
                # This is a folder -- recurse with folder name as category
                folder_name = outline.get("text") or outline.get("title")
                self._parse_outlines(outline, bookmarks, category=folder_name)
