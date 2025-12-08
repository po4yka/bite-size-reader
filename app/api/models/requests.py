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


class SyncSessionRequest(BaseModel):
    """Session creation options."""

    limit: int | None = Field(default=None, ge=1, le=500)


class SyncApplyItem(BaseModel):
    """Single change to upload during sync."""

    entity_type: Literal["summary", "request", "preference", "stat", "crawl_result", "llm_call"]
    id: int | str = Field(description="Server-side identifier for the entity")
    action: Literal["update", "delete"]
    last_seen_version: int = Field(ge=0)
    payload: dict[str, Any] | None = None
    client_timestamp: str | None = Field(default=None, description="Client-side ISO timestamp")


class SyncApplyRequest(BaseModel):
    """Request body for applying local changes."""

    session_id: str
    changes: list[SyncApplyItem]


class CollectionCreateRequest(BaseModel):
    """Request body for creating a collection."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=1)


class CollectionUpdateRequest(BaseModel):
    """Request body for updating a collection."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=1)


class CollectionItemCreateRequest(BaseModel):
    """Request body for adding an item to a collection."""

    summary_id: int


class CollectionReorderRequest(BaseModel):
    """Reorder child collections."""

    items: list[dict[str, int]] = Field(min_length=1)


class CollectionItemReorderRequest(BaseModel):
    """Reorder items inside a collection."""

    items: list[dict[str, int]] = Field(min_length=1)


class CollectionMoveRequest(BaseModel):
    """Move collection to a new parent."""

    parent_id: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=1)


class CollectionItemMoveRequest(BaseModel):
    """Move items to another collection."""

    summary_ids: list[int] = Field(min_length=1)
    target_collection_id: int
    position: int | None = Field(default=None, ge=1)


class CollectionShareRequest(BaseModel):
    """Add collaborator."""

    user_id: int
    role: Literal["editor", "viewer"]


class CollectionInviteRequest(BaseModel):
    """Create invite token."""

    role: Literal["editor", "viewer"]
    expires_at: str | None = None
