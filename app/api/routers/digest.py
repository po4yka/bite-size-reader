"""Digest Mini App REST API router.

All endpoints use Telegram WebApp initData authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request

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
async def list_channels(
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List user's channel subscriptions and slot usage."""
    data = await digest_facade.list_channels(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/channels/subscribe")
async def subscribe_channel(
    body: SubscribeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Subscribe to a Telegram channel."""
    data = await digest_facade.subscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/channels/unsubscribe")
async def unsubscribe_channel(
    body: SubscribeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Unsubscribe from a Telegram channel."""
    data = await digest_facade.unsubscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/channels/resolve")
async def resolve_channel(
    body: ResolveChannelRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Resolve a channel username and return metadata preview."""
    data = await digest_facade.resolve_channel(current_user["user_id"], body.channel_username)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.get("/channels/{username}/posts")
async def list_channel_posts(
    request: Request,
    username: str = Path(..., min_length=5, max_length=32),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List recent posts for a subscribed channel."""
    data = await digest_facade.list_channel_posts(
        current_user["user_id"], username, limit=limit, offset=offset
    )
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/channels/bulk-unsubscribe")
async def bulk_unsubscribe(
    body: BulkUnsubscribeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Unsubscribe from multiple channels at once."""
    data = await digest_facade.bulk_unsubscribe(current_user["user_id"], body.channel_usernames)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.patch("/channels/bulk-category")
async def bulk_assign_category(
    body: BulkCategoryRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Assign multiple subscriptions to a category."""
    data = await digest_facade.bulk_assign_category(
        current_user["user_id"], body.subscription_ids, body.category_id
    )
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.get("/preferences")
async def get_preferences(
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Get merged digest preferences (user overrides + global defaults)."""
    data = await digest_facade.get_preferences(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.patch("/preferences")
async def update_preferences(
    body: UpdatePreferenceRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Update user digest preferences."""
    fields = body.model_dump(exclude_none=True)
    data = await digest_facade.update_preferences(current_user["user_id"], **fields)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.get("/history")
async def list_history(
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Paginated list of past digest deliveries."""
    data = await digest_facade.list_history(current_user["user_id"], limit=limit, offset=offset)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/trigger")
async def trigger_digest(
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Trigger an on-demand digest generation. Result delivered to Telegram chat."""
    data = await digest_facade.trigger_digest(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/trigger-channel")
async def trigger_channel_digest(
    body: SubscribeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Trigger digest for a single channel (equivalent to /cdigest bot command)."""
    await AuthService.require_owner(current_user)

    data = await digest_facade.trigger_channel_digest(
        current_user["user_id"],
        body.channel_username,
    )
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


# --- Categories ---


@router.get("/categories")
async def list_categories(
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """List user's channel categories."""
    data = await digest_facade.list_categories(current_user["user_id"])
    return success_response(
        {"categories": data},
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/categories")
async def create_category(
    body: CategoryRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Create a new channel category."""
    data = await digest_facade.create_category(current_user["user_id"], body.name)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.patch("/categories/{category_id}")
async def update_category(
    body: CategoryRequest,
    request: Request,
    category_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Update a channel category."""
    data = await digest_facade.update_category(current_user["user_id"], category_id, name=body.name)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.delete("/categories/{category_id}")
async def delete_category(
    request: Request,
    category_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Delete a channel category."""
    data = await digest_facade.delete_category(current_user["user_id"], category_id)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.patch("/channels/{subscription_id}/category")
async def assign_category(
    body: AssignCategoryRequest,
    request: Request,
    subscription_id: int = Path(...),
    current_user: dict[str, Any] = Depends(get_webapp_user),
    digest_facade: DigestFacade = Depends(get_digest_facade),
) -> dict[str, Any]:
    """Assign a subscription to a category (or remove with null)."""
    data = await digest_facade.assign_category(
        current_user["user_id"], subscription_id, body.category_id
    )
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
