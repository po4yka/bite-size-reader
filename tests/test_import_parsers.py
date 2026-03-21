"""Tests for bookmark import parsers against fixture files."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.domain.services.import_parsers.csv_parser import CsvBookmarkParser
from app.domain.services.import_parsers.netscape import NetscapeHTMLParser
from app.domain.services.import_parsers.omnivore import OmnivoreParser
from app.domain.services.import_parsers.pocket import PocketParser

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestNetscapeHTMLParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = NetscapeHTMLParser()
        self.bookmarks = self.parser.parse(_read_fixture("netscape_bookmarks.html"))

    def test_correct_count(self) -> None:
        assert len(self.bookmarks) == 3

    def test_urls_extracted(self) -> None:
        urls = [b.url for b in self.bookmarks]
        assert "https://example.com/python" in urls
        assert "https://example.com/rust" in urls
        assert "https://example.com/news" in urls

    def test_titles_extracted(self) -> None:
        titles = [b.title for b in self.bookmarks]
        assert "Learn Python" in titles
        assert "Rust Guide" in titles
        assert "Tech News" in titles

    def test_tags_extracted(self) -> None:
        python_bm = next(b for b in self.bookmarks if b.url == "https://example.com/python")
        assert python_bm.tags == ["python", "tutorial"]

        rust_bm = next(b for b in self.bookmarks if b.url == "https://example.com/rust")
        assert rust_bm.tags == []

    def test_created_at_parsed(self) -> None:
        python_bm = next(b for b in self.bookmarks if b.url == "https://example.com/python")
        assert python_bm.created_at is not None
        assert python_bm.created_at.year == 2023

    def test_collection_name_from_folder(self) -> None:
        python_bm = next(b for b in self.bookmarks if b.url == "https://example.com/python")
        assert python_bm.collection_name == "Programming"

        news_bm = next(b for b in self.bookmarks if b.url == "https://example.com/news")
        assert news_bm.collection_name is None

    def test_empty_input_returns_empty(self) -> None:
        assert self.parser.parse("") == []
        assert self.parser.parse(b"") == []

    def test_malformed_html_does_not_crash(self) -> None:
        result = self.parser.parse("<not><valid>html<<<<")
        assert isinstance(result, list)


class TestPocketParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PocketParser()
        self.bookmarks = self.parser.parse(_read_fixture("pocket_export.html"))

    def test_correct_count(self) -> None:
        assert len(self.bookmarks) == 2

    def test_urls_extracted(self) -> None:
        urls = [b.url for b in self.bookmarks]
        assert "https://example.com/article1" in urls
        assert "https://example.com/article2" in urls

    def test_tags_extracted(self) -> None:
        a1 = next(b for b in self.bookmarks if b.url == "https://example.com/article1")
        assert "read-later" in a1.tags
        assert "tech" in a1.tags

    def test_created_at_parsed(self) -> None:
        a1 = next(b for b in self.bookmarks if b.url == "https://example.com/article1")
        assert a1.created_at is not None

    def test_empty_input_returns_empty(self) -> None:
        assert self.parser.parse("") == []

    def test_malformed_html_does_not_crash(self) -> None:
        result = self.parser.parse("<<<garbage>>>")
        assert isinstance(result, list)


class TestOmnivoreParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = OmnivoreParser()
        self.bookmarks = self.parser.parse(_read_fixture("omnivore_export.json"))

    def test_correct_count(self) -> None:
        assert len(self.bookmarks) == 2

    def test_urls_extracted(self) -> None:
        urls = [b.url for b in self.bookmarks]
        assert "https://example.com/omni1" in urls
        assert "https://example.com/omni2" in urls

    def test_titles_extracted(self) -> None:
        titles = [b.title for b in self.bookmarks]
        assert "Omnivore Article 1" in titles
        assert "Omnivore Article 2" in titles

    def test_tags_from_labels(self) -> None:
        omni1 = next(b for b in self.bookmarks if b.url == "https://example.com/omni1")
        assert "ai" in omni1.tags
        assert "research" in omni1.tags

    def test_created_at_parsed(self) -> None:
        omni1 = next(b for b in self.bookmarks if b.url == "https://example.com/omni1")
        assert omni1.created_at is not None
        assert omni1.created_at.year == 2024
        assert omni1.created_at.month == 1

    def test_highlights_parsed(self) -> None:
        omni1 = next(b for b in self.bookmarks if b.url == "https://example.com/omni1")
        assert omni1.highlights is not None
        assert len(omni1.highlights) == 1
        assert omni1.highlights[0]["quote"] == "important text"

        omni2 = next(b for b in self.bookmarks if b.url == "https://example.com/omni2")
        assert omni2.highlights is None

    def test_empty_input_returns_empty(self) -> None:
        assert self.parser.parse("") == []
        assert self.parser.parse("{}") == []

    def test_malformed_json_does_not_crash(self) -> None:
        result = self.parser.parse("{not json at all")
        assert result == []

    def test_non_list_json_returns_empty(self) -> None:
        result = self.parser.parse('{"key": "value"}')
        assert result == []


class TestCsvBookmarkParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = CsvBookmarkParser()
        self.bookmarks = self.parser.parse(_read_fixture("generic_import.csv"))

    def test_correct_count(self) -> None:
        assert len(self.bookmarks) == 3

    def test_urls_extracted(self) -> None:
        urls = [b.url for b in self.bookmarks]
        assert "https://example.com/csv1" in urls
        assert "https://example.com/csv2" in urls
        assert "https://example.com/csv3" in urls

    def test_titles_extracted(self) -> None:
        csv1 = next(b for b in self.bookmarks if b.url == "https://example.com/csv1")
        assert csv1.title == "CSV Article 1"

    def test_tags_extracted(self) -> None:
        csv1 = next(b for b in self.bookmarks if b.url == "https://example.com/csv1")
        assert "python" in csv1.tags
        assert "data" in csv1.tags

    def test_notes_extracted(self) -> None:
        csv1 = next(b for b in self.bookmarks if b.url == "https://example.com/csv1")
        assert csv1.notes == "A note about python"

        csv2 = next(b for b in self.bookmarks if b.url == "https://example.com/csv2")
        assert csv2.notes is None

    def test_created_at_parsed(self) -> None:
        csv1 = next(b for b in self.bookmarks if b.url == "https://example.com/csv1")
        assert csv1.created_at is not None
        assert csv1.created_at.year == 2024

    def test_missing_created_at_is_none(self) -> None:
        csv3 = next(b for b in self.bookmarks if b.url == "https://example.com/csv3")
        assert csv3.created_at is None

    def test_empty_input_returns_empty(self) -> None:
        assert self.parser.parse("") == []

    def test_malformed_csv_does_not_crash(self) -> None:
        result = self.parser.parse("no,headers,match\na,b,c")
        assert isinstance(result, list)


if __name__ == "__main__":
    unittest.main()
