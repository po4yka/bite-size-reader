"""Tests for OPML feed list exporter."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from app.domain.services.import_export.opml_exporter import OPMLExporter


class TestOPMLExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.exporter = OPMLExporter()

    def test_basic_export(self) -> None:
        feeds = [{"url": "https://example.com/feed.xml", "title": "Example"}]
        result = self.exporter.serialize(feeds)
        root = ET.fromstring(result)
        assert root.tag == "opml"
        assert root.get("version") == "2.0"
        assert root.find("head") is not None
        assert root.find("body") is not None

    def test_categorized_feeds(self) -> None:
        feeds = [
            {"url": "https://a.com/feed", "title": "Feed A", "category_name": "Tech"},
            {"url": "https://b.com/feed", "title": "Feed B", "category_name": "Tech"},
            {"url": "https://c.com/feed", "title": "Feed C", "category_name": "News"},
        ]
        result = self.exporter.serialize(feeds)
        root = ET.fromstring(result)
        body = root.find("body")
        assert body is not None

        folders = body.findall("outline")
        # Should have folder outlines for "News" and "Tech"
        folder_names = {f.get("text") for f in folders if f.findall("outline")}
        assert "Tech" in folder_names
        assert "News" in folder_names

        # Tech folder should have 2 feeds
        tech_folder = next(f for f in folders if f.get("text") == "Tech")
        assert len(tech_folder.findall("outline")) == 2

    def test_uncategorized_feeds(self) -> None:
        feeds = [
            {"url": "https://example.com/feed.xml", "title": "Uncategorized"},
        ]
        result = self.exporter.serialize(feeds)
        root = ET.fromstring(result)
        body = root.find("body")
        assert body is not None

        # Uncategorized feeds should be at top level of body
        top_outlines = body.findall("outline")
        assert len(top_outlines) == 1
        assert top_outlines[0].get("xmlUrl") == "https://example.com/feed.xml"

    def test_xml_attributes(self) -> None:
        feeds = [
            {
                "url": "https://example.com/feed.xml",
                "title": "My Feed",
                "site_url": "https://example.com",
            },
        ]
        result = self.exporter.serialize(feeds)
        root = ET.fromstring(result)
        body = root.find("body")
        assert body is not None
        outline = body.find("outline")
        assert outline is not None
        assert outline.get("xmlUrl") == "https://example.com/feed.xml"
        assert outline.get("htmlUrl") == "https://example.com"
        assert outline.get("type") == "rss"
        assert outline.get("text") == "My Feed"
        assert outline.get("title") == "My Feed"

    def test_empty_feeds(self) -> None:
        result = self.exporter.serialize([])
        root = ET.fromstring(result)
        assert root.tag == "opml"
        body = root.find("body")
        assert body is not None
        assert len(body.findall("outline")) == 0


if __name__ == "__main__":
    unittest.main()
