"""Digest Mini App REST API router.

All endpoints use Telegram WebApp initData authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from app.api.models.digest import (  # noqa: TC001 - used at runtime by FastAPI
    AssignCategoryRequest,
    BulkCategoryRequest,
    BulkUnsubscribeRequest,
    CategoryRequest,
    ResolveChannelRequest,
    SubscribeRequest,
    UpdatePreferenceRequest,
)
from app.api.models.responses import success_response
from app.api.routers.auth.dependencies import get_webapp_user
from app.api.services.auth_service import AuthService
from app.api.services.digest_facade import DigestFacade, get_digest_facade

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/channels")
def list_channels(
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List user's channel subscriptions and slot usage."""
    data = digest_facade.list_channels(current_user["user_id"])
    return success_response(data)


@router.post("/channels/subscribe")
def subscribe_channel(
    body: SubscribeRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Subscribe to a Telegram channel."""
    data = digest_facade.subscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(data)


@router.post("/channels/unsubscribe")
def unsubscribe_channel(
    body: SubscribeRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Unsubscribe from a Telegram channel."""
    data = digest_facade.unsubscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(data)


@router.post("/channels/resolve")
async def resolve_channel(
    body: ResolveChannelRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Resolve a channel username and return metadata preview."""
    data = await digest_facade.resolve_channel(current_user["user_id"], body.channel_username)
    return success_response(data)


@router.get("/channels/{username}/posts")
def list_channel_posts(
    username: str = Path(..., min_length=5, max_length=32),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List recent posts for a subscribed channel."""
    data = digest_facade.list_channel_posts(
        current_user["user_id"], username, limit=limit, offset=offset
    )
    return success_response(data)


@router.post("/channels/bulk-unsubscribe")
def bulk_unsubscribe(
    body: BulkUnsubscribeRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Unsubscribe from multiple channels at once."""
    data = digest_facade.bulk_unsubscribe(current_user["user_id"], body.channel_usernames)
    return success_response(data)


@router.patch("/channels/bulk-category")
def bulk_assign_category(
    body: BulkCategoryRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Assign multiple subscriptions to a category."""
    data = digest_facade.bulk_assign_category(
        current_user["user_id"], body.subscription_ids, body.category_id
    )
    return success_response(data)


@router.get("/preferences")
def get_preferences(
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Get merged digest preferences (user overrides + global defaults)."""
    data = digest_facade.get_preferences(current_user["user_id"])
    return success_response(data)


@router.patch("/preferences")
def update_preferences(
    body: UpdatePreferenceRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Update user digest preferences."""
    fields = body.model_dump(exclude_none=True)
    data = digest_facade.update_preferences(current_user["user_id"], **fields)
    return success_response(data)


@router.get("/history")
def list_history(
    current_user: dict[str, Any] = Depends(get_webapp_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Paginated list of past digest deliveries."""
    data = digest_facade.list_history(current_user["user_id"], limit=limit, offset=offset)
    return success_response(data)


@router.post("/trigger")
def trigger_digest(
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Trigger an on-demand digest generation. Result delivered to Telegram chat."""
    data = digest_facade.trigger_digest(current_user["user_id"])
    return success_response(data)


@router.post("/trigger-channel")
async def trigger_channel_digest(
    body: SubscribeRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Trigger digest for a single channel (equivalent to /cdigest bot command)."""
    await AuthService.require_owner(current_user)

    data = await digest_facade.trigger_channel_digest(
        current_user["user_id"],
        body.channel_username,
    )
    return success_response(data)


# --- Categories ---


@router.get("/categories")
def list_categories(
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List user's channel categories."""
    data = digest_facade.list_categories(current_user["user_id"])
    return success_response({"categories": data})


@router.post("/categories")
def create_category(
    body: CategoryRequest,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Create a new channel category."""
    data = digest_facade.create_category(current_user["user_id"], body.name)
    return success_response(data)


@router.patch("/categories/{category_id}")
def update_category(
    body: CategoryRequest,
    category_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Update a channel category."""
    data = digest_facade.update_category(current_user["user_id"], category_id, name=body.name)
    return success_response(data)


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Delete a channel category."""
    data = digest_facade.delete_category(current_user["user_id"], category_id)
    return success_response(data)


@router.patch("/channels/{subscription_id}/category")
def assign_category(
    body: AssignCategoryRequest,
    subscription_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Assign a subscription to a category (or remove with null)."""
    data = digest_facade.assign_category(current_user["user_id"], subscription_id, body.category_id)
    return success_response(data)
