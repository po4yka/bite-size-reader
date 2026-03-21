"""Shared context builder for summary evaluation.

Used by both the rule engine and smart collections to build
the evaluation context dict from summary and request data.
"""

from __future__ import annotations

import json
from typing import Any


def build_summary_context(
    summary_dict: dict[str, Any] | None,
    request_dict: dict[str, Any] | None,
    tag_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build evaluation context from summary and request data.

    Returns dict with keys: url, title, tags, language, reading_time,
    source_type, content.
    """
    json_payload = (summary_dict or {}).get("json_payload") or {}
    if isinstance(json_payload, str):
        try:
            json_payload = json.loads(json_payload)
        except (json.JSONDecodeError, TypeError):
            json_payload = {}

    return {
        "url": (request_dict or {}).get("normalized_url")
        or (request_dict or {}).get("input_url", ""),
        "title": json_payload.get("title", ""),
        "tags": tag_names or json_payload.get("topic_tags", []),
        "language": (summary_dict or {}).get("lang", ""),
        "reading_time": json_payload.get("estimated_reading_time_min", 0),
        "source_type": json_payload.get("source_type", ""),
        "content": json_payload.get("summary_1000", "") or json_payload.get("summary_250", ""),
    }
