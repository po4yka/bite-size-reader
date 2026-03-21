"""Base types for bookmark import parsers.

These are pure data containers and a protocol -- no DB or network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class ImportedBookmark:
    url: str
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    created_at: datetime | None = None
    collection_name: str | None = None
    highlights: list[dict] | None = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class BookmarkParser(Protocol):
    def parse(self, content: str | bytes) -> list[ImportedBookmark]: ...
