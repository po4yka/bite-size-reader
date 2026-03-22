"""Tests for import file format detection.

Covers FormatDetector.detect across all supported formats:
csv, opml, netscape_html, pocket, omnivore, linkwarden, karakeep, and unknown.
"""

from __future__ import annotations

import json

from app.domain.services.import_export.format_detector import FormatDetector


class TestFormatDetectorCSV:
    def test_csv_extension(self) -> None:
        assert FormatDetector.detect("bookmarks.csv", b"url,title\n") == "csv"

    def test_csv_extension_uppercase(self) -> None:
        assert FormatDetector.detect("BOOKMARKS.CSV", b"url,title\n") == "csv"


class TestFormatDetectorOPML:
    def test_opml_extension(self) -> None:
        assert FormatDetector.detect("feeds.opml", b"<opml>") == "opml"

    def test_xml_with_opml_tag(self) -> None:
        content = b'<?xml version="1.0"?>\n<opml version="2.0"><head/><body/></opml>'
        assert FormatDetector.detect("feeds.xml", content) == "opml"

    def test_xml_without_opml_tag(self) -> None:
        content = b'<?xml version="1.0"?>\n<rss><channel/></rss>'
        assert FormatDetector.detect("feeds.xml", content) == "unknown"


class TestFormatDetectorHTML:
    def test_netscape_html(self) -> None:
        content = b"<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<META"
        assert FormatDetector.detect("bookmarks.html", content) == "netscape_html"

    def test_netscape_htm_extension(self) -> None:
        content = b"<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL>"
        assert FormatDetector.detect("bookmarks.htm", content) == "netscape_html"

    def test_pocket_html(self) -> None:
        content = (
            b"<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
            b"<h1>Bookmarks</h1>\n"
            b"<DL><p><DT><A HREF='https://example.com'>Example</A></DT></p></DL>"
        )
        assert FormatDetector.detect("bookmarks.html", content) == "pocket"

    def test_pocket_html_getpocket_link(self) -> None:
        content = b"<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL>exported from getpocket.com</DL>"
        assert FormatDetector.detect("bookmarks.html", content) == "pocket"

    def test_html_without_netscape_doctype(self) -> None:
        content = b"<html><body><a href='https://example.com'>link</a></body></html>"
        assert FormatDetector.detect("page.html", content) == "unknown"


class TestFormatDetectorJSON:
    def test_karakeep_format(self) -> None:
        content = json.dumps({"bookmarks": [{"url": "https://test.com"}]}).encode()
        assert FormatDetector.detect("export.json", content) == "karakeep"

    def test_omnivore_format(self) -> None:
        content = json.dumps([{"url": "https://test.com", "labels": [{"name": "tag"}]}]).encode()
        assert FormatDetector.detect("export.json", content) == "omnivore"

    def test_linkwarden_format(self) -> None:
        content = json.dumps(
            [
                {
                    "url": "https://test.com",
                    "tags": [{"name": "tag"}],
                    "collection": {"name": "folder"},
                }
            ]
        ).encode()
        assert FormatDetector.detect("export.json", content) == "linkwarden"

    def test_empty_json_content(self) -> None:
        assert FormatDetector.detect("empty.json", b"") == "unknown"

    def test_malformed_json(self) -> None:
        assert FormatDetector.detect("bad.json", b"not json{{{") == "unknown"

    def test_json_dict_without_bookmarks_key(self) -> None:
        content = json.dumps({"items": [{"url": "https://test.com"}]}).encode()
        assert FormatDetector.detect("export.json", content) == "unknown"

    def test_json_empty_list(self) -> None:
        content = json.dumps([]).encode()
        assert FormatDetector.detect("export.json", content) == "unknown"

    def test_json_list_without_labels_or_collection(self) -> None:
        content = json.dumps([{"url": "https://test.com", "title": "Test"}]).encode()
        assert FormatDetector.detect("export.json", content) == "unknown"

    def test_linkwarden_needs_tag_name_field(self) -> None:
        """Linkwarden detection requires tags[0] to be a dict with 'name'."""
        content = json.dumps(
            [
                {
                    "url": "https://test.com",
                    "tags": ["plain-string"],
                    "collection": {"name": "folder"},
                }
            ]
        ).encode()
        assert FormatDetector.detect("export.json", content) == "unknown"


class TestFormatDetectorUnknown:
    def test_unknown_extension(self) -> None:
        assert FormatDetector.detect("file.xyz", b"random data") == "unknown"

    def test_no_extension(self) -> None:
        assert FormatDetector.detect("noext", b"some content") == "unknown"

    def test_empty_filename(self) -> None:
        assert FormatDetector.detect("", b"some content") == "unknown"
