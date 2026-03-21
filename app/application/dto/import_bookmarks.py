"""DTOs for bookmark import workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.services.import_parsers.base import ImportedBookmark


@dataclass(frozen=True, slots=True)
class ImportBookmarksCommand:
    job_id: int
    bookmarks: list[ImportedBookmark]
    user_id: int
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BookmarkImportItemResult:
    url: str
    outcome: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ImportProgressSnapshot:
    processed: int
    created: int
    skipped: int
    failed: int
    errors: list[str] = field(default_factory=list)
    status: str | None = None
