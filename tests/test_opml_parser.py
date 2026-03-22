"""Tests for OPML feed list parser."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.domain.services.import_parsers.opml import OPMLParser

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestOPMLParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = OPMLParser()

    def test_parse_basic_opml(self) -> None:
        bookmarks = self.parser.parse(_read_fixture("sample_feeds.opml"))
        assert len(bookmarks) == 3

    def test_folder_hierarchy(self) -> None:
        bookmarks = self.parser.parse(_read_fixture("sample_feeds.opml"))
        tech_feeds = [b for b in bookmarks if b.collection_name == "Tech"]
        assert len(tech_feeds) == 2
        urls = {b.url for b in tech_feeds}
        assert "https://hnrss.org/frontpage" in urls
        assert "https://lobste.rs/rss" in urls

    def test_uncategorized_feed(self) -> None:
        bookmarks = self.parser.parse(_read_fixture("sample_feeds.opml"))
        uncategorized = [b for b in bookmarks if b.collection_name is None]
        assert len(uncategorized) == 1
        assert uncategorized[0].url == "https://example.com/feed.xml"

    def test_empty_opml(self) -> None:
        content = '<?xml version="1.0"?><opml version="2.0"><head/><body/></opml>'
        bookmarks = self.parser.parse(content)
        assert bookmarks == []

    def test_invalid_xml(self) -> None:
        bookmarks = self.parser.parse("not valid xml at all <><>")
        assert bookmarks == []

    def test_extra_metadata(self) -> None:
        bookmarks = self.parser.parse(_read_fixture("sample_feeds.opml"))
        hn = next(b for b in bookmarks if "hnrss" in b.url)
        assert hn.extra.get("html_url") == "https://news.ycombinator.com"
        assert hn.extra.get("feed_type") == "rss"
        assert hn.extra.get("outline_type") == "rss"


if __name__ == "__main__":
    unittest.main()
