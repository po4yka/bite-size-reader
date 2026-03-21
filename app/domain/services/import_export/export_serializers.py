"""Export serializers for summaries.

Pure functions -- no DB or network access. Stdlib only.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import UTC, datetime


class JsonExporter:
    """Serialize summaries to JSON."""

    @staticmethod
    def serialize(
        summaries: list[dict],
        tags: list[dict] | None = None,
        collections: list[dict] | None = None,
    ) -> str:
        payload = {
            "version": 1,
            "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summaries": [_enrich_summary(s) for s in summaries],
            "tags": tags or [],
            "collections": collections or [],
        }
        return json.dumps(payload, indent=2, default=str, ensure_ascii=False)


class CsvExporter:
    """Serialize summaries to CSV."""

    _HEADERS = ["url", "title", "tags", "language", "created_at", "is_read", "is_favorited"]

    @staticmethod
    def serialize(
        summaries: list[dict],
        tags: list[dict] | None = None,
        collections: list[dict] | None = None,
    ) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CsvExporter._HEADERS, extrasaction="ignore")
        writer.writeheader()
        for s in summaries:
            writer.writerow(
                {
                    "url": s.get("url", ""),
                    "title": s.get("title", ""),
                    "tags": ";".join(_tag_names(s)),
                    "language": s.get("language", ""),
                    "created_at": s.get("created_at", ""),
                    "is_read": s.get("is_read", False),
                    "is_favorited": s.get("is_favorited", False),
                }
            )
        return buf.getvalue()


class NetscapeHtmlExporter:
    """Serialize summaries to Netscape bookmark HTML."""

    @staticmethod
    def serialize(
        summaries: list[dict],
        tags: list[dict] | None = None,
        collections: list[dict] | None = None,
    ) -> str:
        lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>Bookmarks</TITLE>",
            "<H1>Bookmarks</H1>",
            "<DL><p>",
        ]
        for s in summaries:
            url = html.escape(s.get("url", ""), quote=True)
            title = html.escape(s.get("title", ""), quote=True)
            add_date = _to_unix_ts(s.get("created_at"))
            tag_str = ",".join(_tag_names(s))

            attrs = f'HREF="{url}"'
            if add_date is not None:
                attrs += f' ADD_DATE="{add_date}"'
            if tag_str:
                attrs += f' TAGS="{html.escape(tag_str, quote=True)}"'

            lines.append(f"<DT><A {attrs}>{title}</A>")

        lines.append("</DL><p>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tag_names(summary: dict) -> list[str]:
    """Extract tag name strings from a summary dict."""
    raw = summary.get("tags")
    if not raw:
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("name", "")
            if name:
                result.append(name)
    return result


def _enrich_summary(s: dict) -> dict:
    """Return a copy of the summary dict with canonical export keys."""
    return {
        "url": s.get("url", ""),
        "title": s.get("title", ""),
        "tags": _tag_names(s),
        "collections": _collection_names(s),
        "language": s.get("language", ""),
        "is_read": s.get("is_read", False),
        "is_favorited": s.get("is_favorited", False),
        "created_at": s.get("created_at", ""),
        "summary_json": s.get("summary_json") or s.get("json_payload"),
        "highlights": s.get("highlights", []),
        "reading_progress": s.get("reading_progress"),
    }


def _collection_names(summary: dict) -> list[str]:
    """Extract collection name strings from a summary dict."""
    raw = summary.get("collections")
    if not raw:
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("name", "")
            if name:
                result.append(name)
    return result


def _to_unix_ts(value: object) -> int | None:
    """Convert a datetime or ISO string to Unix timestamp."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None
    return None
