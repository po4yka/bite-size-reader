"""Pydantic models for Karakeep API."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic needs this at runtime

from pydantic import BaseModel, Field


class KarakeepTag(BaseModel):
    """Karakeep tag model."""

    id: str
    name: str
    count: int | None = None


class KarakeepBookmark(BaseModel):
    """Karakeep bookmark model."""

    id: str
    type: str = "link"  # link, text, asset
    url: str | None = None
    title: str | None = None
    note: str | None = None
    summary: str | None = None
    content: dict | str | None = None  # Can be nested object or string
    tags: list[KarakeepTag] = Field(default_factory=list)
    archived: bool = False
    favourited: bool = False
    created_at: datetime | None = Field(default=None, alias="createdAt")
    modified_at: datetime | None = Field(default=None, alias="modifiedAt")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class KarakeepBookmarkList(BaseModel):
    """Paginated list of bookmarks."""

    bookmarks: list[KarakeepBookmark] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, alias="nextCursor")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class CreateBookmarkRequest(BaseModel):
    """Request to create a new bookmark."""

    type: str = "link"
    url: str
    title: str | None = None
    note: str | None = None


class AttachTagRequest(BaseModel):
    """Request to attach tags to a bookmark."""

    tags: list[dict[str, str]]  # [{"tagName": "tag1"}, ...]


class SyncResult(BaseModel):
    """Result of a sync operation."""

    direction: str  # 'bsr_to_karakeep' or 'karakeep_to_bsr'
    items_synced: int = 0
    items_skipped: int = 0
    items_failed: int = 0
    errors: list[str] = Field(default_factory=list)
    retryable_errors: list[str] = Field(default_factory=list)
    permanent_errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


class FullSyncResult(BaseModel):
    """Result of a full bidirectional sync."""

    bsr_to_karakeep: SyncResult
    karakeep_to_bsr: SyncResult
    total_synced: int = 0
    total_duration_seconds: float = 0.0
