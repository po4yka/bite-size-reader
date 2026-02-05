"""Work item models used during sync orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.adapters.karakeep.models import KarakeepBookmark


@dataclass
class _SyncWorkItem:
    """Internal work item for BSR-to-Karakeep sync."""

    summary_data: dict[str, Any]
    url_hash: str
    existing_bookmark: KarakeepBookmark | None = None
