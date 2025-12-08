from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.routers.auth import get_current_user
from app.db.models import User, UserDevice, _utcnow

router = APIRouter()


class BaseResponse(BaseModel):
    status: str


class DeviceRegistrationPayload(BaseModel):
    token: str = Field(..., description="FCM or APNS device token")
    platform: str = Field(..., description="Platform: 'ios' or 'android'")
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
    user = User.get_or_none(User.telegram_user_id == user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if this token exists
    device = UserDevice.get_or_none(UserDevice.token == payload.token)

    if device:
        # Update existing device info
        device.user = user
        device.platform = payload.platform
        device.device_id = payload.device_id
        device.last_seen_at = _utcnow()
        device.is_active = True
        device.save()
    else:
        # Create new device record
        UserDevice.create(
            user=user,
            token=payload.token,
            platform=payload.platform,
            device_id=payload.device_id,
            is_active=True,
            last_seen_at=_utcnow(),
        )

    return BaseResponse(status="ok")
