"""
Pydantic models for API request validation.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator


class SubmitURLRequest(BaseModel):
    """Request body for submitting a URL."""

    type: Literal["url"] = "url"
    input_url: HttpUrl
    lang_preference: Literal["auto", "en", "ru"] = "auto"

    @field_validator("input_url")
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate URL scheme."""
        url_str = str(v)
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class ForwardMetadata(BaseModel):
    """Metadata for forwarded message."""

    from_chat_id: int
    from_message_id: int
    from_chat_title: str | None = None
    forwarded_at: str | None = None


class SubmitForwardRequest(BaseModel):
    """Request body for submitting a forwarded message."""

    type: Literal["forward"] = "forward"
    content_text: str = Field(min_length=10, max_length=100000)
    forward_metadata: ForwardMetadata
    lang_preference: Literal["auto", "en", "ru"] = "auto"


class UpdateSummaryRequest(BaseModel):
    """Request body for updating a summary."""

    is_read: bool | None = None


class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""

    lang_preference: Literal["auto", "en", "ru"] | None = None
    notification_settings: dict[str, Any] | None = None
    app_settings: dict[str, Any] | None = None


class SyncUploadChange(BaseModel):
    """Single change to upload during sync."""

    summary_id: int
    action: Literal["update", "delete"]
    fields: dict[str, Any] | None = None
    client_timestamp: str


class SyncUploadRequest(BaseModel):
    """Request body for uploading local changes."""

    changes: list[SyncUploadChange]
    device_id: str
    last_sync: str
