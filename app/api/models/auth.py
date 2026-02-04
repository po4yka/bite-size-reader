"""
Pydantic models for authentication API.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelegramLoginRequest(BaseModel):
    """Request body for Telegram login."""

    model_config = ConfigDict(populate_by_name=True)

    telegram_user_id: int = Field(..., alias="id")
    auth_hash: str = Field(..., alias="hash")
    auth_date: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    client_id: str = Field(
        ...,
        description="Client application ID (e.g., 'android-app-v1.0', 'ios-app-v2.0')",
        min_length=1,
        max_length=100,
    )


class AppleLoginRequest(BaseModel):
    """Request body for Apple login."""

    id_token: str
    client_id: str
    authorization_code: str | None = None
    given_name: str | None = None
    family_name: str | None = None


class GoogleLoginRequest(BaseModel):
    """Request body for Google login."""

    id_token: str
    client_id: str


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class SecretLoginRequest(BaseModel):
    """Request body for secret-key login."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    client_id: str = Field(..., min_length=1, max_length=100)
    secret: str = Field(..., min_length=8)
    username: str | None = None


class SecretKeyCreateRequest(BaseModel):
    """Request body to create or register a client secret."""

    user_id: int
    client_id: str = Field(..., min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None
    secret: str | None = Field(
        default=None,
        description="Optional client-generated secret; if omitted, server will generate",
    )
    username: str | None = None


class SecretKeyRotateRequest(BaseModel):
    """Request body to rotate an existing client secret."""

    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None
    secret: str | None = Field(
        default=None,
        description="Optional client-generated secret; if omitted, server will generate",
    )


class SecretKeyRevokeRequest(BaseModel):
    """Request body to revoke an existing client secret."""

    reason: str | None = Field(default=None, max_length=200)


class ClientSecretInfo(BaseModel):
    """Safe representation of a stored client secret (no hash included)."""

    id: int
    user_id: int
    client_id: str
    status: str
    label: str | None = None
    description: str | None = None
    expires_at: str | None = None
    last_used_at: str | None = None
    failed_attempts: int
    locked_until: str | None = None
    created_at: str
    updated_at: str


class SecretKeyCreateResponse(BaseModel):
    """Payload returned when creating or rotating a secret key."""

    secret: str
    key: ClientSecretInfo


class SecretKeyActionResponse(BaseModel):
    """Payload for list/revoke actions."""

    key: ClientSecretInfo


class SecretKeyListResponse(BaseModel):
    """Payload for listing stored secrets."""

    keys: list[ClientSecretInfo]


class TelegramLinkStatus(BaseModel):
    """Link status payload."""

    linked: bool
    telegram_user_id: int | None = None
    username: str | None = None
    photo_url: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linked_at: str | None = None
    link_nonce_expires_at: str | None = None
    link_nonce: str | None = None


class TelegramLinkBeginResponse(BaseModel):
    """Begin link payload with nonce."""

    nonce: str
    expires_at: str


class TelegramLinkCompleteRequest(TelegramLoginRequest):
    """Complete linking using Telegram login payload + nonce."""

    nonce: str


class SessionInfo(BaseModel):
    """Session information for active sessions list."""

    id: int
    client_id: str | None = Field(serialization_alias="clientId")
    device_info: str | None = Field(serialization_alias="deviceInfo")
    ip_address: str | None = Field(serialization_alias="ipAddress")
    last_used_at: str | None = Field(serialization_alias="lastUsedAt")
    created_at: str = Field(serialization_alias="createdAt")
    is_current: bool = Field(default=False, serialization_alias="isCurrent")
