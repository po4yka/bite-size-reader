"""Bookmark import format parsers.

Each parser is a pure function (no DB, no network) that converts an export
format into a list of ImportedBookmark dataclasses.
"""

from app.domain.services.import_parsers.base import BookmarkParser, ImportedBookmark
from app.domain.services.import_parsers.csv_parser import CsvBookmarkParser
from app.domain.services.import_parsers.karakeep_parser import KarakeepParser
from app.domain.services.import_parsers.linkwarden import LinkwardenParser
from app.domain.services.import_parsers.netscape import NetscapeHTMLParser
from app.domain.services.import_parsers.omnivore import OmnivoreParser
from app.domain.services.import_parsers.pocket import PocketParser

PARSER_REGISTRY: dict[str, type[BookmarkParser]] = {
    "netscape_html": NetscapeHTMLParser,
    "pocket": PocketParser,
    "omnivore": OmnivoreParser,
    "linkwarden": LinkwardenParser,
    "karakeep": KarakeepParser,
    "csv": CsvBookmarkParser,
}

__all__ = [
    "PARSER_REGISTRY",
    "BookmarkParser",
    "CsvBookmarkParser",
    "ImportedBookmark",
    "KarakeepParser",
    "LinkwardenParser",
    "NetscapeHTMLParser",
    "OmnivoreParser",
    "PocketParser",
]
