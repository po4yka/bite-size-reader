"""Database synchronization endpoints for offline mobile support."""

from fastapi import APIRouter, Depends, Query

from app.api.models.requests import SyncApplyRequest, SyncSessionRequest
from app.api.models.responses import SyncApplyResult, SyncPage, success_response
from app.api.routers.auth import get_current_user
from app.api.services.sync_service import SyncService
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()

_cfg: AppConfig | None = None


def _get_cfg() -> AppConfig:
    global _cfg
    if _cfg is None:
        _cfg = load_config(allow_stub_telegram=True)
    return _cfg


def _pagination(page: SyncPage) -> dict:
    total = len(page.created) + len(page.updated) + len(page.deleted)
    return {
        "total": total,
        "limit": page.limit,
        "offset": 0,
        "has_more": page.has_more,
    }


@router.post("/sessions")
async def create_sync_session(
    body: SyncSessionRequest | None = None,
    user=Depends(get_current_user),
) -> dict:
    """Create or resume a sync session."""
    svc = SyncService(_get_cfg())
    session = await svc.start_session(
        user_id=user["user_id"],
        client_id=user.get("client_id"),
        limit=body.limit if body else None,
    )

    pagination = {"total": 0, "limit": session.chunk_limit, "offset": 0, "has_more": True}
    return success_response(session, pagination=pagination)


@router.get("/full")
async def full_sync(
    session_id: str = Query(..., description="Sync session identifier"),
    limit: int | None = Query(None, ge=1, le=500),
    user=Depends(get_current_user),
) -> dict:
    """Fetch full sync data in bounded chunks."""
    svc = SyncService(_get_cfg())
    page = await svc.get_full(
        session_id=session_id,
        user_id=user["user_id"],
        client_id=user.get("client_id"),
        limit=limit,
    )
    return success_response(page, pagination=_pagination(page))


@router.get("/delta")
async def delta_sync(
    session_id: str = Query(..., description="Sync session identifier"),
    since: int = Query(..., ge=0, description="Last seen server_version cursor"),
    limit: int | None = Query(None, ge=1, le=500),
    user=Depends(get_current_user),
) -> dict:
    """Fetch delta sync (created/updated/deleted) since a cursor."""
    svc = SyncService(_get_cfg())
    page = await svc.get_delta(
        session_id=session_id,
        user_id=user["user_id"],
        client_id=user.get("client_id"),
        since=since,
        limit=limit,
    )
    return success_response(page, pagination=_pagination(page))


@router.post("/apply")
async def apply_changes(
    payload: SyncApplyRequest,
    user=Depends(get_current_user),
) -> dict:
    """Apply client-side changes with conflict detection."""
    svc = SyncService(_get_cfg())
    result: SyncApplyResult = await svc.apply_changes(
        session_id=payload.session_id,
        user_id=user["user_id"],
        client_id=user.get("client_id"),
        changes=payload.changes,
    )
    return success_response(result)
