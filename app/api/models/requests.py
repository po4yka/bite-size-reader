"""
Pydantic models for API request validation.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, validator


class SubmitURLRequest(BaseModel):
    """Request body for submitting a URL."""

    type: str = Field(default="url", const=True)
    input_url: HttpUrl
    lang_preference: str = Field(default="auto", regex="^(auto|en|ru)$")

    @validator("input_url")
    def validate_url(cls, v):
        """Validate URL scheme."""
        if not str(v).startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class ForwardMetadata(BaseModel):
    """Metadata for forwarded message."""

    from_chat_id: int
    from_message_id: int
    from_chat_title: Optional[str] = None
    forwarded_at: Optional[str] = None


class SubmitForwardRequest(BaseModel):
    """Request body for submitting a forwarded message."""

    type: str = Field(default="forward", const=True)
    content_text: str = Field(min_length=10, max_length=100000)
    forward_metadata: ForwardMetadata
    lang_preference: str = Field(default="auto", regex="^(auto|en|ru)$")


class UpdateSummaryRequest(BaseModel):
    """Request body for updating a summary."""

    is_read: Optional[bool] = None


class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""

    lang_preference: Optional[str] = Field(None, regex="^(auto|en|ru)$")
    notification_settings: Optional[Dict[str, Any]] = None
    app_settings: Optional[Dict[str, Any]] = None


class SyncUploadChange(BaseModel):
    """Single change to upload during sync."""

    summary_id: int
    action: str = Field(regex="^(update|delete)$")
    fields: Optional[Dict[str, Any]] = None
    client_timestamp: str


class SyncUploadRequest(BaseModel):
    """Request body for uploading local changes."""

    changes: list[SyncUploadChange]
    device_id: str
    last_sync: str
