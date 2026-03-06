"""Digest Mini App REST API router.

All endpoints use Telegram WebApp initData authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.models.digest import SubscribeRequest, UpdatePreferenceRequest  # noqa: TC001
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
    data = digest_facade.list_channels(current_user["user_id"])
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
    data = digest_facade.subscribe_channel(current_user["user_id"], body.channel_username)
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
    data = digest_facade.unsubscribe_channel(current_user["user_id"], body.channel_username)
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
    data = digest_facade.get_preferences(current_user["user_id"])
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
    data = digest_facade.update_preferences(current_user["user_id"], **fields)
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
    data = digest_facade.list_history(current_user["user_id"], limit=limit, offset=offset)
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
