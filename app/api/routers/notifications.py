from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies.database import get_device_repository
from app.api.routers.auth import get_current_user
from app.core.logging_utils import get_logger
from app.infrastructure.persistence.sqlite.repositories.device_repository import (  # noqa: TC001 - used at runtime by FastAPI
    SqliteDeviceRepositoryAdapter,
)

logger = get_logger(__name__)

router = APIRouter()


class BaseResponse(BaseModel):
    status: str


class DeviceRegistrationPayload(BaseModel):
    token: str = Field(..., min_length=1, max_length=500, description="FCM or APNS device token")
    platform: Literal["ios", "android"] = Field(..., description="Platform: 'ios' or 'android'")
    device_id: str | None = Field(None, description="Unique device identifier (optional)")

    model_config = ConfigDict(extra="ignore")


@router.post("/device", response_model=BaseResponse)
async def register_device(
    payload: DeviceRegistrationPayload,
    user_data: Annotated[dict, Depends(get_current_user)],
    device_repo: SqliteDeviceRepositoryAdapter = Depends(get_device_repository),
):
    """
    Register or update a device token for push notifications.
    """
    user_id = user_data["user_id"]

    try:
        await device_repo.async_upsert_device(
            user_id=user_id,
            token=payload.token,
            platform=payload.platform,
            device_id=payload.device_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

    return BaseResponse(status="ok")
