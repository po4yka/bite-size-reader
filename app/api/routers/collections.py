"""
Collections management endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

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
    PaginationInfo,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.api.services.collection_service import CollectionService
from app.core.logging_utils import get_logger

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
    collections = await CollectionService.list_collections(
        user_id=user["user_id"], parent_id=parent_id, limit=limit, offset=offset
    )
    data = [
        CollectionResponse(
            id=c["id"],
            name=c["name"],
            description=c.get("description"),
            parent_id=c.get("parent_id") or c.get("parent"),
            position=c.get("position"),
            created_at=_isotime(c.get("created_at")),
            updated_at=_isotime(c.get("updated_at")),
            server_version=c.get("server_version"),
            is_shared=bool(c.get("is_shared", False)),
            share_count=c.get("share_count"),
            item_count=c.get("item_count", 0),
        )
        for c in collections
    ]
    pagination = PaginationInfo(
        total=len(data),
        limit=limit,
        offset=offset,
        has_more=len(data) == limit,
    )
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
        collection = await CollectionService.create_collection(
            user_id=user["user_id"],
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            position=body.position,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return success_response(
        CollectionResponse(
            id=collection["id"],
            name=collection["name"],
            description=collection.get("description"),
            parent_id=collection.get("parent_id") or collection.get("parent"),
            position=collection.get("position"),
            created_at=_isotime(collection.get("created_at")),
            updated_at=_isotime(collection.get("updated_at")),
            server_version=collection.get("server_version"),
            is_shared=bool(collection.get("is_shared", False)),
            share_count=collection.get("share_count"),
        )
    )


@router.get("/{collection_id}")
async def get_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Get collection details."""
    collection = await CollectionService.get_collection_with_auth(
        collection_id, user["user_id"], "viewer"
    )

    return success_response(
        CollectionResponse(
            id=collection["id"],
            name=collection["name"],
            description=collection.get("description"),
            parent_id=collection.get("parent_id") or collection.get("parent"),
            position=collection.get("position"),
            created_at=_isotime(collection.get("created_at")),
            updated_at=_isotime(collection.get("updated_at")),
            server_version=collection.get("server_version"),
            is_shared=bool(collection.get("is_shared", False)),
            share_count=collection.get("share_count"),
            item_count=collection.get("item_count", 0),
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
        collection = await CollectionService.update_collection(
            collection_id=collection_id,
            user_id=user["user_id"],
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            position=body.position,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return success_response(
        CollectionResponse(
            id=collection["id"],
            name=collection["name"],
            description=collection.get("description"),
            parent_id=collection.get("parent_id") or collection.get("parent"),
            position=collection.get("position"),
            created_at=_isotime(collection.get("created_at")),
            updated_at=_isotime(collection.get("updated_at")),
            server_version=collection.get("server_version"),
            is_shared=bool(collection.get("is_shared", False)),
            share_count=collection.get("share_count"),
        )
    )


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: int,
    user=Depends(get_current_user),
):
    """Delete a collection (soft delete)."""
    await CollectionService.delete_collection(collection_id, user["user_id"])
    return success_response({"success": True})


@router.post("/{collection_id}/items")
async def add_collection_item(
    collection_id: int,
    body: CollectionItemCreateRequest,
    user=Depends(get_current_user),
):
    """Add a summary to a collection."""
    await CollectionService.add_item(collection_id, body.summary_id, user["user_id"])
    return success_response({"success": True})


@router.get("/{collection_id}/items")
async def list_collection_items(
    collection_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    items = await CollectionService.list_items(collection_id, user["user_id"], limit, offset)
    payload = [
        CollectionItem(
            collection_id=item.get("collection_id") or item.get("collection"),
            summary_id=item.get("summary_id") or item.get("summary"),
            position=item.get("position"),
            created_at=_isotime(item.get("created_at")),
        )
        for item in items
    ]
    pagination = PaginationInfo(
        total=len(payload),
        limit=limit,
        offset=offset,
        has_more=len(payload) == limit,
    )
    return success_response(
        CollectionItemsResponse(items=payload, pagination=pagination), pagination=pagination
    )


@router.post("/{collection_id}/items/reorder")
async def reorder_collection_items(
    collection_id: int,
    body: CollectionItemReorderRequest,
    user=Depends(get_current_user),
):
    await CollectionService.reorder_items(collection_id, user["user_id"], body.items)
    return success_response({"success": True})


@router.post("/{collection_id}/items/move")
async def move_collection_items(
    collection_id: int,
    body: CollectionItemMoveRequest,
    user=Depends(get_current_user),
):
    moved = await CollectionService.move_items(
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
    await CollectionService.remove_item(collection_id, summary_id, user["user_id"])
    return success_response({"success": True})


@router.post("/{collection_id}/reorder")
async def reorder_collections(
    collection_id: int,
    body: CollectionReorderRequest,
    user=Depends(get_current_user),
):
    await CollectionService.reorder_collections(
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
        moved = await CollectionService.move_collection(
            collection_id=collection_id,
            user_id=user["user_id"],
            parent_id=body.parent_id,
            position=body.position,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return success_response(
        CollectionMoveResponse(
            id=moved["id"],
            parent_id=moved.get("parent_id") or moved.get("parent"),
            position=moved.get("position") or 0,
            server_version=moved.get("server_version"),
            updated_at=_isotime(moved.get("updated_at")),
        )
    )


@router.get("/tree")
async def get_collection_tree(
    max_depth: int = Query(3, ge=1, le=10),
    user=Depends(get_current_user),
):
    tree = await CollectionService.get_tree(user_id=user["user_id"], max_depth=max_depth)

    def to_response(col: dict) -> CollectionResponse:
        children = col.get("_children") or []
        return CollectionResponse(
            id=col["id"],
            name=col["name"],
            description=col.get("description"),
            parent_id=col.get("parent_id") or col.get("parent"),
            position=col.get("position"),
            created_at=_isotime(col.get("created_at")),
            updated_at=_isotime(col.get("updated_at")),
            server_version=col.get("server_version"),
            is_shared=bool(col.get("is_shared", False)),
            share_count=col.get("share_count"),
            item_count=col.get("item_count", 0),
            children=[to_response(c) for c in children],
        )

    data = [to_response(c) for c in tree]
    return success_response({"collections": data})


@router.get("/{collection_id}/acl")
async def get_collection_acl(collection_id: int, user=Depends(get_current_user)):
    acl = await CollectionService.list_acl(collection_id, user["user_id"])
    payload = []
    for entry in acl:
        # Get user_id from nested owner_user dict or direct user_id field
        entry_user_id = entry.get("user_id")
        if entry.get("owner_user"):
            entry_user_id = entry["owner_user"].get("telegram_user_id", entry_user_id)
        elif entry.get("user"):
            user_data = entry["user"]
            if isinstance(user_data, dict):
                entry_user_id = user_data.get("telegram_user_id", entry_user_id)

        # Get invited_by user id
        invited_by_id = None
        if entry.get("invited_by"):
            invited_by_data = entry["invited_by"]
            if isinstance(invited_by_data, dict):
                invited_by_id = invited_by_data.get("telegram_user_id")
            elif isinstance(invited_by_data, int):
                invited_by_id = invited_by_data

        payload.append(
            CollectionAclEntry(
                user_id=entry_user_id,
                role=entry.get("role", "owner"),
                status=entry.get("status", "active"),
                invited_by=invited_by_id,
                created_at=_isotime(entry.get("created_at")) if entry.get("created_at") else None,
                updated_at=_isotime(entry.get("updated_at")) if entry.get("updated_at") else None,
            )
        )
    return success_response(CollectionAclResponse(acl=payload))


@router.post("/{collection_id}/share")
async def add_collection_collaborator(
    collection_id: int,
    body: CollectionShareRequest,
    user=Depends(get_current_user),
):
    await CollectionService.add_collaborator(
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
    await CollectionService.remove_collaborator(
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
    invite = await CollectionService.create_invite(
        collection_id=collection_id,
        user_id=user["user_id"],
        role=body.role,
        expires_at=expires,
    )
    return success_response(
        {"token": invite.get("token"), "role": invite.get("role"), "expires_at": body.expires_at}
    )


@router.post("/invites/{token}/accept")
async def accept_collection_invite(
    token: str,
    user=Depends(get_current_user),
):
    await CollectionService.accept_invite(token=token, user_id=user["user_id"])
    return success_response({"success": True})
