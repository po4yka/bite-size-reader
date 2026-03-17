"""Push notification (Firebase) configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PushNotificationConfig(BaseModel):
    """Firebase push notification configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=False, validation_alias="PUSH_NOTIFICATIONS_ENABLED")
    firebase_credentials_path: str = Field(
        default="",
        validation_alias="FIREBASE_CREDENTIALS_PATH",
        description="Path to Firebase service account JSON file",
    )

    @field_validator("firebase_credentials_path", mode="before")
    @classmethod
    def _validate_credentials_path(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        path = str(value).strip()
        if len(path) > 1000:
            msg = "Firebase credentials path appears to be too long"
            raise ValueError(msg)
        return path
