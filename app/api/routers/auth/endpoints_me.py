"""
Current-user endpoints (profile + account management).
"""

from __future__ import annotations

from typing import Any

from app.api.exceptions import ProcessingError
from app.api.models.responses import UserInfo, success_response
from app.api.routers.auth._fastapi import APIRouter, Depends
from app.api.routers.auth.dependencies import get_current_user
from app.api.services.auth_service import AuthService
from app.core.logging_utils import get_logger
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

logger = get_logger(__name__)
router = APIRouter()


def _format_dt_z(dt_value: Any) -> str:
    if not dt_value:
        return ""
    if isinstance(dt_value, str):
        return dt_value if dt_value.endswith("Z") else dt_value + "Z"
    if hasattr(dt_value, "isoformat"):
        return dt_value.isoformat() + "Z"
    return str(dt_value) if str(dt_value).endswith("Z") else str(dt_value) + "Z"


@router.get("/me")
async def get_current_user_info(user=Depends(get_current_user)):
    """Get current authenticated user information."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user_record, _ = await user_repo.async_get_or_create_user(
        user["user_id"],
        username=user.get("username"),
        is_owner=False,
    )

    return success_response(
        UserInfo(
            user_id=user["user_id"],
            username=user.get("username") or "",
            client_id=user["client_id"],
            is_owner=user_record.get("is_owner", False),
            created_at=_format_dt_z(user_record.get("created_at")),
        )
    )


@router.delete("/me")
async def delete_account(user=Depends(get_current_user)):
    """Delete the current user account and all associated data."""
    user_id = user["user_id"]
    await AuthService.ensure_user(user_id)

    try:
        await AuthService.delete_user(user_id)
        logger.info("user_deleted_account", extra={"user_id": user_id})
        return success_response({"success": True})
    except Exception as e:
        logger.error("delete_account_failed", extra={"user_id": user_id}, exc_info=True)
        raise ProcessingError("Failed to delete account") from e
