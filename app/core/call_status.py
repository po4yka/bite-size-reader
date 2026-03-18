"""Status enum for LLM and scraper call results."""

from __future__ import annotations

from enum import StrEnum


class CallStatus(StrEnum):
    """High-level result status for LLM and content scraper calls."""

    OK = "ok"
    ERROR = "error"
