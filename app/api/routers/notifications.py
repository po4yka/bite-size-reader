from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.routers.auth import get_current_user
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.device_repository import (
    SqliteDeviceRepositoryAdapter,
)

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
):
    """
    Register or update a device token for push notifications.
    """
    user_id = user_data["user_id"]
    device_repo = SqliteDeviceRepositoryAdapter(database_proxy)

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
