"""
Collections management endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from peewee import IntegrityError

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import (
    CollectionCreateRequest,
    CollectionItemCreateRequest,
    CollectionUpdateRequest,
)
from app.api.models.responses import (
    CollectionListResponse,
    CollectionResponse,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import Collection, CollectionItem, Summary

logger = get_logger(__name__)
router = APIRouter()


def _isotime(dt) -> str:
    """Safely convert datetime to ISO string."""
    if hasattr(dt, "isoformat"):
        return dt.isoformat() + "Z"
    return str(dt)


@router.get("")
async def get_collections(
    user=Depends(get_current_user),
):
    """List all collections for the current user."""
    collections = (
        Collection.select()
        .where(Collection.user_id == user["user_id"])
        .order_by(Collection.updated_at.desc())
    )

    return success_response(
        CollectionListResponse(
            collections=[
                CollectionResponse(
                    id=c.id,
                    name=c.name,
                    description=c.description,
                    created_at=_isotime(c.created_at),
                    updated_at=_isotime(c.updated_at),
                    server_version=c.server_version,
                )
                for c in collections
            ]
        )
    )


@router.post("")
async def create_collection(
    body: CollectionCreateRequest,
    user=Depends(get_current_user),
):
    """Create a new collection."""
    try:
        collection = Collection.create(
            user_id=user["user_id"],
            name=body.name,
            description=body.description,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail="Collection with this name already exists"
        ) from err

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
        )
    )


@router.get("/{collection_id}")
async def get_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Get collection details."""
    collection = (
        Collection.select()
        .where((Collection.id == collection_id) & (Collection.user_id == user["user_id"]))
        .first()
    )

    if not collection:
        raise ResourceNotFoundError("Collection", collection_id)

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
        )
    )


@router.patch("/{collection_id}")
async def update_collection(
    collection_id: int,
    body: CollectionUpdateRequest,
    user=Depends(get_current_user),
):
    """Update a collection."""
    collection = (
        Collection.select()
        .where((Collection.id == collection_id) & (Collection.user_id == user["user_id"]))
        .first()
    )

    if not collection:
        raise ResourceNotFoundError("Collection", collection_id)

    if body.name is not None:
        collection.name = body.name
    if body.description is not None:
        collection.description = body.description

    collection.updated_at = datetime.now(UTC)
    try:
        collection.save()
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail="Collection with this name already exists"
        ) from err

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
        )
    )


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Delete a collection."""
    query = Collection.delete().where(
        (Collection.id == collection_id) & (Collection.user_id == user["user_id"])
    )
    deleted_count = query.execute()

    if deleted_count == 0:
        raise ResourceNotFoundError("Collection", collection_id)

    return success_response({"success": True})


@router.post("/{collection_id}/items")
async def add_collection_item(
    collection_id: int,
    body: CollectionItemCreateRequest,
    user=Depends(get_current_user),
):
    """Add a summary to a collection."""
    # Verify collection ownership
    collection = (
        Collection.select()
        .where((Collection.id == collection_id) & (Collection.user_id == user["user_id"]))
        .first()
    )
    if not collection:
        raise ResourceNotFoundError("Collection", collection_id)

    # Verify summary existence (and ownership ideally, or at least visibility)
    # Assuming any visible summary can be collected
    summary = Summary.get_or_none(Summary.id == body.summary_id)
    if not summary:
        raise ResourceNotFoundError("Summary", body.summary_id)

    try:
        CollectionItem.create(
            collection=collection,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        # Update collection timestamp
        collection.updated_at = datetime.now(UTC)
        collection.save()
    except IntegrityError:
        # Already exists, just ignore
        pass

    return success_response({"success": True})


@router.delete("/{collection_id}/items/{summary_id}")
async def remove_collection_item(
    collection_id: int,
    summary_id: int,
    user=Depends(get_current_user),
):
    """Remove a summary from a collection."""
    # Verify collection ownership
    collection = (
        Collection.select()
        .where((Collection.id == collection_id) & (Collection.user_id == user["user_id"]))
        .first()
    )
    if not collection:
        raise ResourceNotFoundError("Collection", collection_id)

    query = CollectionItem.delete().where(
        (CollectionItem.collection == collection) & (CollectionItem.summary_id == summary_id)
    )
    deleted_count = query.execute()

    if deleted_count > 0:
        # Update collection timestamp
        collection.updated_at = datetime.now(UTC)
        collection.save()

    return success_response({"success": True})
