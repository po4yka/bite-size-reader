"""Pocket bookmark export parser.

Pocket uses the Netscape HTML format with the same TAGS attribute convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.services.import_parsers.netscape import NetscapeHTMLParser

if TYPE_CHECKING:
    from app.domain.services.import_parsers.base import ImportedBookmark


class PocketParser:
    """Parse Pocket HTML exports (Netscape-compatible format)."""

    def parse(self, content: str | bytes) -> list[ImportedBookmark]:
        return NetscapeHTMLParser().parse(content)
