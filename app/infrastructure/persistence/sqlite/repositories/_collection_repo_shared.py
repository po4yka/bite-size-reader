"""Shared helpers for the SQLite collection repository."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import Collection, CollectionCollaborator, CollectionItem, model_to_dict

logger = get_logger(__name__)


def _now() -> dt.datetime:
    """Get the current UTC time."""
    return dt.datetime.now(UTC)


def _get_active_collection(collection_id: int) -> Collection | None:
    """Return a non-deleted collection by ID."""
    return Collection.get_or_none((Collection.id == collection_id) & (~Collection.is_deleted))


def _get_collection_item_count(collection_id: int) -> int:
    """Return the number of items in a collection."""
    return CollectionItem.select().where(CollectionItem.collection == collection_id).count()


def _serialize_collection(collection: Collection) -> dict[str, Any]:
    """Serialize a collection and attach its item count."""
    data = model_to_dict(collection) or {}
    data["item_count"] = _get_collection_item_count(collection.id)
    return data


def _recompute_share_state(collection: Collection) -> None:
    """Refresh collection sharing flags after collaborator changes."""
    collection.share_count = (
        CollectionCollaborator.select()
        .where(
            (CollectionCollaborator.collection == collection)
            & (CollectionCollaborator.status == "active")
        )
        .count()
    )
    collection.is_shared = collection.share_count > 0
    collection.save()
