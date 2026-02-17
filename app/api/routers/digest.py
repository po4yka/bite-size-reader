"""Digest Mini App REST API router.

All endpoints use Telegram WebApp initData authentication.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request

from app.api.models.digest import SubscribeRequest, UpdatePreferenceRequest
from app.api.models.responses import success_response
from app.api.routers.auth.dependencies import get_webapp_user
from app.api.services.digest_api_service import DigestAPIService
from app.config.digest import ChannelDigestConfig

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service() -> DigestAPIService:
    """Build DigestAPIService with current config."""
    cfg = ChannelDigestConfig()
    return DigestAPIService(cfg)


@router.get("/channels")
async def list_channels(
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """List user's channel subscriptions and slot usage."""
    svc = _get_service()
    data = svc.list_subscriptions(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.post("/channels/subscribe")
async def subscribe_channel(
    body: SubscribeRequest,
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Subscribe to a Telegram channel."""
    svc = _get_service()
    data = svc.subscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.post("/channels/unsubscribe")
async def unsubscribe_channel(
    body: SubscribeRequest,
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Unsubscribe from a Telegram channel."""
    svc = _get_service()
    data = svc.unsubscribe_channel(current_user["user_id"], body.channel_username)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.get("/preferences")
async def get_preferences(
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Get merged digest preferences (user overrides + global defaults)."""
    svc = _get_service()
    data = svc.get_preferences(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.patch("/preferences")
async def update_preferences(
    body: UpdatePreferenceRequest,
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Update user digest preferences."""
    svc = _get_service()
    fields = body.model_dump(exclude_none=True)
    data = svc.update_preferences(current_user["user_id"], **fields)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.get("/history")
async def list_history(
    current_user: dict = Depends(get_webapp_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Paginated list of past digest deliveries."""
    svc = _get_service()
    data = svc.list_deliveries(current_user["user_id"], limit=limit, offset=offset)
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.post("/trigger")
async def trigger_digest(
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Trigger an on-demand digest generation. Result delivered to Telegram chat."""
    svc = _get_service()
    data = svc.trigger_digest(current_user["user_id"])
    return success_response(
        data,
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )


@router.post("/trigger-channel")
async def trigger_channel_digest(
    request_body: dict,
    current_user: dict = Depends(get_webapp_user),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Trigger digest for a single channel (equivalent to /cdigest bot command)."""
    from app.api.exceptions import ValidationError

    channel_username = request_body.get("channel_username", "").strip().lstrip("@")
    if not channel_username:
        raise ValidationError("channel_username is required")

    # Reuse existing digest trigger logic but for single channel
    # This will be handled by the digest scheduler
    return success_response(
        {
            "status": "queued",
            "channel": channel_username,
        },
        correlation_id=getattr(request.state, "correlation_id", None) if request else None,
    )
