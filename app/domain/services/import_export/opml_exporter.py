"""OPML feed list exporter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any


class OPMLExporter:
    """Export RSS feed subscriptions as OPML 2.0 XML."""

    def serialize(
        self,
        feeds: list[dict[str, Any]],
        categories: list[dict[str, Any]] | None = None,
    ) -> str:
        opml = ET.Element("opml", version="2.0")
        head = ET.SubElement(opml, "head")
        ET.SubElement(head, "title").text = "Ratatoskr Feed Subscriptions"
        ET.SubElement(head, "dateCreated").text = datetime.now(UTC).strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        body = ET.SubElement(opml, "body")

        # Group feeds by category
        categorized: dict[str, list[dict]] = {}
        uncategorized: list[dict] = []
        for feed in feeds:
            cat = feed.get("category_name")
            if cat:
                categorized.setdefault(cat, []).append(feed)
            else:
                uncategorized.append(feed)

        # Uncategorized feeds at top level
        for feed in uncategorized:
            self._add_feed_outline(body, feed)

        # Categorized feeds in folders
        for cat_name, cat_feeds in sorted(categorized.items()):
            folder = ET.SubElement(body, "outline", text=cat_name, title=cat_name)
            for feed in cat_feeds:
                self._add_feed_outline(folder, feed)

        tree = ET.ElementTree(opml)
        ET.indent(tree, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(opml, encoding="unicode")

    def _add_feed_outline(self, parent: ET.Element, feed: dict[str, Any]) -> None:
        attrs = {
            "type": "rss",
            "text": feed.get("title") or feed.get("url", ""),
            "title": feed.get("title") or feed.get("url", ""),
            "xmlUrl": feed.get("url", ""),
        }
        if feed.get("site_url"):
            attrs["htmlUrl"] = feed["site_url"]
        ET.SubElement(parent, "outline", **attrs)
