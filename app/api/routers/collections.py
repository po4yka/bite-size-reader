"""
Collections management endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from peewee import IntegrityError

from app.api.exceptions import ResourceNotFoundError
from app.api.models.requests import (
    CollectionCreateRequest,
    CollectionInviteRequest,
    CollectionItemCreateRequest,
    CollectionItemMoveRequest,
    CollectionItemReorderRequest,
    CollectionMoveRequest,
    CollectionReorderRequest,
    CollectionShareRequest,
    CollectionUpdateRequest,
)
from app.api.models.responses import (
    CollectionAclEntry,
    CollectionAclResponse,
    CollectionItem,
    CollectionItemsMoveResponse,
    CollectionItemsResponse,
    CollectionListResponse,
    CollectionMoveResponse,
    CollectionResponse,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.api.services.collection_service import CollectionService
from app.core.logging_utils import get_logger
from app.db.models import Collection

logger = get_logger(__name__)
router = APIRouter()


def _isotime(dt) -> str:
    """Safely convert datetime to ISO string."""
    if hasattr(dt, "isoformat"):
        return dt.isoformat() + "Z"
    return str(dt)


@router.get("")
async def get_collections(
    parent_id: int | None = Query(default=None, ge=1),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    """List collections for the current user (and collaborations) under a parent."""
    if not isinstance(parent_id, (int, type(None))):
        parent_id = None
    if not isinstance(limit, int):
        limit = 20
    if not isinstance(offset, int):
        offset = 0
    collections = CollectionService.list_collections(
        user_id=user["user_id"], parent_id=parent_id, limit=limit, offset=offset
    )
    data = [
        CollectionResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            parent_id=c.parent_id,
            position=c.position,
            created_at=_isotime(c.created_at),
            updated_at=_isotime(c.updated_at),
            server_version=c.server_version,
            is_shared=bool(getattr(c, "is_shared", False)),
            share_count=getattr(c, "share_count", None),
            item_count=c.items.count(),
        )
        for c in collections
    ]
    pagination = {
        "total": len(data),
        "limit": limit,
        "offset": offset,
        "has_more": len(data) == limit,
    }
    return success_response(
        CollectionListResponse(collections=data, pagination=pagination),
        pagination=pagination,
    )


@router.post("")
async def create_collection(
    body: CollectionCreateRequest,
    user=Depends(get_current_user),
):
    """Create a new collection."""
    try:
        collection = CollectionService.create_collection(
            user_id=user["user_id"],
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            position=body.position,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail="Collection with this name already exists"
        ) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            parent_id=collection.parent_id,
            position=collection.position,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
            is_shared=bool(collection.is_shared),
            share_count=getattr(collection, "share_count", None),
        )
    )


@router.get("/{collection_id}")
async def get_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Get collection details."""
    collection = Collection.get_or_none(
        (Collection.id == collection_id) & (Collection.is_deleted == False)  # noqa: E712
    )

    if not collection:
        raise ResourceNotFoundError("Collection", collection_id)
    CollectionService._require_role(collection, user["user_id"], "viewer")

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            parent_id=collection.parent_id,
            position=collection.position,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
            is_shared=bool(collection.is_shared),
            share_count=getattr(collection, "share_count", None),
            item_count=collection.items.count(),
        )
    )


@router.patch("/{collection_id}")
async def update_collection(
    collection_id: int,
    body: CollectionUpdateRequest,
    user=Depends(get_current_user),
):
    """Update a collection."""
    try:
        collection = CollectionService.update_collection(
            collection_id=collection_id,
            user_id=user["user_id"],
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            position=body.position,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail="Collection with this name already exists"
        ) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return success_response(
        CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            parent_id=collection.parent_id,
            position=collection.position,
            created_at=_isotime(collection.created_at),
            updated_at=_isotime(collection.updated_at),
            server_version=collection.server_version,
            is_shared=bool(collection.is_shared),
            share_count=getattr(collection, "share_count", None),
        )
    )


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Delete a collection (soft delete)."""
    CollectionService.delete_collection(collection_id, user["user_id"])
    return success_response({"success": True})


@router.post("/{collection_id}/items")
async def add_collection_item(
    collection_id: int,
    body: CollectionItemCreateRequest,
    user=Depends(get_current_user),
):
    """Add a summary to a collection."""
    CollectionService.add_item(collection_id, body.summary_id, user["user_id"])
    return success_response({"success": True})


@router.get("/{collection_id}/items")
async def list_collection_items(
    collection_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    items = CollectionService.list_items(collection_id, user["user_id"], limit, offset)
    payload = [
        CollectionItem(
            collection_id=item.collection_id,
            summary_id=item.summary_id,
            position=item.position,
            created_at=_isotime(item.created_at),
        )
        for item in items
    ]
    pagination = {
        "total": None,
        "limit": limit,
        "offset": offset,
        "has_more": len(payload) == limit,
    }
    return success_response(
        CollectionItemsResponse(items=payload, pagination=pagination), pagination=pagination
    )


@router.post("/{collection_id}/items/reorder")
async def reorder_collection_items(
    collection_id: int,
    body: CollectionItemReorderRequest,
    user=Depends(get_current_user),
):
    CollectionService.reorder_items(collection_id, user["user_id"], body.items)
    return success_response({"success": True})


@router.post("/{collection_id}/items/move")
async def move_collection_items(
    collection_id: int,
    body: CollectionItemMoveRequest,
    user=Depends(get_current_user),
):
    moved = CollectionService.move_items(
        source_collection_id=collection_id,
        user_id=user["user_id"],
        summary_ids=body.summary_ids,
        target_collection_id=body.target_collection_id,
        position=body.position,
    )
    return success_response(CollectionItemsMoveResponse(moved_summary_ids=moved))


@router.delete("/{collection_id}/items/{summary_id}")
async def remove_collection_item(
    collection_id: int,
    summary_id: int,
    user=Depends(get_current_user),
):
    """Remove a summary from a collection."""
    CollectionService.remove_item(collection_id, summary_id, user["user_id"])
    return success_response({"success": True})


@router.post("/{collection_id}/reorder")
async def reorder_collections(
    collection_id: int,
    body: CollectionReorderRequest,
    user=Depends(get_current_user),
):
    CollectionService.reorder_collections(
        parent_id=collection_id,
        user_id=user["user_id"],
        items=body.items,
    )
    return success_response({"success": True})


@router.post("/{collection_id}/move")
async def move_collection(
    collection_id: int,
    body: CollectionMoveRequest,
    user=Depends(get_current_user),
):
    try:
        moved = CollectionService.move_collection(
            collection_id=collection_id,
            user_id=user["user_id"],
            parent_id=body.parent_id,
            position=body.position,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return success_response(
        CollectionMoveResponse(
            id=moved.id,
            parent_id=moved.parent_id,
            position=moved.position or 0,
            server_version=moved.server_version,
            updated_at=_isotime(moved.updated_at),
        )
    )


@router.get("/tree")
async def get_collection_tree(
    max_depth: int = Query(3, ge=1, le=10),
    user=Depends(get_current_user),
):
    tree = CollectionService.get_tree(user_id=user["user_id"], max_depth=max_depth)

    def to_response(col: Collection):
        children = getattr(col, "_children", None) or []
        return CollectionResponse(
            id=col.id,
            name=col.name,
            description=col.description,
            parent_id=col.parent_id,
            position=col.position,
            created_at=_isotime(col.created_at),
            updated_at=_isotime(col.updated_at),
            server_version=col.server_version,
            is_shared=bool(col.is_shared),
            share_count=getattr(col, "share_count", None),
            item_count=col.items.count(),
            children=[to_response(c) for c in children],
        )

    data = [to_response(c) for c in tree]
    return success_response({"collections": data})


@router.get("/{collection_id}/acl")
async def get_collection_acl(collection_id: int, user=Depends(get_current_user)):
    acl = CollectionService.list_acl(collection_id, user["user_id"])
    payload = []
    for entry in acl:
        payload.append(
            CollectionAclEntry(
                user_id=getattr(entry.user, "telegram_user_id", None)
                if hasattr(entry, "user")
                else None,
                role=getattr(entry, "role", "owner"),
                status=getattr(entry, "status", "active"),
                invited_by=getattr(entry.invited_by, "telegram_user_id", None)
                if hasattr(entry, "invited_by")
                else None,
                created_at=_isotime(getattr(entry, "created_at", None))
                if hasattr(entry, "created_at")
                else None,
                updated_at=_isotime(getattr(entry, "updated_at", None))
                if hasattr(entry, "updated_at")
                else None,
            )
        )
    return success_response(CollectionAclResponse(acl=payload))


@router.post("/{collection_id}/share")
async def add_collection_collaborator(
    collection_id: int,
    body: CollectionShareRequest,
    user=Depends(get_current_user),
):
    CollectionService.add_collaborator(
        collection_id=collection_id,
        user_id=user["user_id"],
        target_user_id=body.user_id,
        role=body.role,
    )
    return success_response({"success": True})


@router.delete("/{collection_id}/share/{target_user_id}")
async def remove_collection_collaborator(
    collection_id: int,
    target_user_id: int,
    user=Depends(get_current_user),
):
    CollectionService.remove_collaborator(
        collection_id=collection_id, user_id=user["user_id"], target_user_id=target_user_id
    )
    return success_response({"success": True})


@router.post("/{collection_id}/invite")
async def create_collection_invite(
    collection_id: int,
    body: CollectionInviteRequest,
    user=Depends(get_current_user),
):
    expires = None
    if body.expires_at:
        try:
            expires = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at") from None
    invite = CollectionService.create_invite(
        collection_id=collection_id,
        user_id=user["user_id"],
        role=body.role,
        expires_at=expires,
    )
    return success_response(
        {"token": invite.token, "role": invite.role, "expires_at": body.expires_at}
    )


@router.post("/invites/{token}/accept")
async def accept_collection_invite(
    token: str,
    user=Depends(get_current_user),
):
    CollectionService.accept_invite(token=token, user_id=user["user_id"])
    return success_response({"success": True})
